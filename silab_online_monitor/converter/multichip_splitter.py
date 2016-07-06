import sys
import zmq
from online_monitor.converter.transceiver import Transceiver
from zmq.utils import jsonapi
import numpy as np

# pyBAR related imports
from pybar_fei4_interpreter.data_interpreter import PyDataInterpreter

from online_monitor.utils import utils


class MultichipSplitter(Transceiver):

    def setup_interpretation(self):
        self.interpreter = PyDataInterpreter()
        self.interpreter.set_warning_output(False)

    def deserialze_data(self, data):  # According to pyBAR data serilization
        try:
            self.meta_data = jsonapi.loads(data)
        except ValueError:
            try:
                dtype = self.meta_data.pop('dtype')
                shape = self.meta_data.pop('shape')
                if self.meta_data:
                    try:
                        raw_data_array = np.frombuffer(buffer(data), dtype=dtype).reshape(shape)
                        return raw_data_array
                    except (KeyError, ValueError):  # KeyError happens if meta data read is omitted; ValueError if np.frombuffer fails due to wrong sha
                        return None
            except AttributeError:  # Happens if first data is not meta data
                return None
        return {'meta_data': self.meta_data}

    def interpret_data(self, data):
        if isinstance(data[0][1], dict):  # Meta data is saved for next raw data send
            return

        raw_data = data[0][1]
        splitted_data = [None] * len(self.backends)
        
        for backend_index in range(len(self.backends)):
            selection = np.bitwise_and(raw_data, 0x0F000000) == np.left_shift(backend_index, 24)
            splitted_data[backend_index] = raw_data[selection]

        return splitted_data

    def serialze_data(self, data):
        return np.zeros(10)
        #return jsonapi.dumps(data, cls=utils.NumpyEncoder)
        if 'hits' in data:
            hits_data  = data['hits']
            data['hits'] = None
            return utils.simple_enc(hits_data, data)
        else:
            return utils.simple_enc(None, data)
        
    def send_data(self, data):  # This function sends for each iterable in data the data over the corresponding backend in pyBAR style
        for backend_index, frontend_data in enumerate(data):
            data_meta_data = self.meta_data
            data_meta_data['dtype'] = str(frontend_data.dtype)
            data_meta_data['shape'] = frontend_data.shape
            try:
                self.backends[backend_index][1].send_json(data_meta_data, flags=zmq.SNDMORE | zmq.NOBLOCK)
                self.backends[backend_index][1].send(frontend_data, flags=zmq.NOBLOCK)  # PyZMQ supports sending numpy arrays without copying any data
            except zmq.Again:
                pass
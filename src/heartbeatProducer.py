import threading
import time
import traceback
import json
import datetime
import logging
import uuid

import simpleProducer

class HeatbeatProducer(object):
    def __init__(self, status_producer, delay, id, stop_event, processor_type):
        self._producer = status_producer
        self._delay = delay
        self._id = id
        self._stop = stop_event        
        self._thread = threading.Thread(target=self.run, daemon = True)
        self._sequence_nr = 0
        self._processor_type = processor_type

    def start(self):
        self._thread.start()        

    def stop(self):
        self._stop.set()

    def run(self):
        request={
            "id" : uuid.uuid1(),                
            "sequence_nr" : self._sequence_nr,
            "processor_id" : self._id,
            "processor_type" : self._processor_type,
            "result": "start",                 
        }
        logging.debug("Sending request {}".format(request))
        try:
            self._producer.send( 
                key=self._id, 
                value=request)
            self._sequence_nr += 1                  
        except:
            logging.error("Error sending heartbeat {}".format(self._id))    
            logging.debug(traceback.format_exc())

        while not self._stop.wait(self._delay):
            request={
                "id" : uuid.uuid1(),                
                "sequence_nr" : self._sequence_nr,
                "processor_id" : self._id,
                "processer_type" : self._processor_type,
                "result": "heartbeat",                 
            }
            logging.debug("Sending request {}".format(request))
            try:
                self._producer.send( 
                    key=self._id, 
                    value=request)
                self._sequence_nr += 1                  
            except:
                logging.error("Error sending heartbeat {}".format(self._id))    
                logging.debug(traceback.format_exc()) 

        request={
            "id" : uuid.uuid1(),                
            "sequence_nr" : self._sequence_nr,
            "processor_id" : self._id,
            "processer_type" : self._processor_type,
            "result": "stop",                 
        }
        logging.debug("Sending request {}".format(request))
        try:
            self._producer.send( 
                key=self._id, 
                value=request)
            self._sequence_nr += 1                  
        except:
            logging.error("Error sending heartbeat {}".format(self._id))    
            logging.debug(traceback.format_exc())         
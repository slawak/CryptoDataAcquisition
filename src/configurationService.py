import etcd3
import logging
import threading
import datetime
import uuid
import traceback
import json

import version
import simpleProducer

DEFAULT_HOST="etcd"
DEFAULT_PORT=2379
DEFAULT_LEADER_KEY = 'leader'
DEFAULT_LEASE_TTL = 5
DEFAULT_SLEEP = 1

DEFAULT_ETCD_ROOT = "CryptoDataAnalyzer"
DIR_VALUE = "."


def combine_path(pathes):
    if not pathes:
        return
    if len(pathes) == 1:
        return pathes[0]
    path = pathes[0].rstrip("/") + "/"
    for part in [p for p in pathes[1:] if p]:
        part = part.rstrip("/")
        if part:
            path += part.rstrip("/") + "/"
    if pathes[-1].rstrip("/") == pathes[-1]:
        path = path.rstrip("/")
    return path

def deserialize(value):
    value = value.decode("utf-8")
    if value == DIR_VALUE:
        return None
    try:
        result = json.loads(value) if value != None else None
    except ValueError:
        result = value
    return result

class EtcdConfigurationService(object):
    def __init__(self, etcd_host, etcd_port, root, 
                processor_type,
                stop_event = None,  
                id=None, 
                leader_election_enabled=True,
                registration_enabled=True):
        self._id = id or uuid.uuid1()
        self._etcd_host = etcd_host
        self._etcd_port = etcd_port
        self.root = combine_path([root, processor_type])
        self.leader_key = combine_path([self.root, DEFAULT_LEADER_KEY])        
        self._processor_type = processor_type
        self._register_lease = None
        self.leader_event = threading.Event()
        self.work_callback = lambda leader: True
        self.leader_callback = lambda: True
        self.follower_callback = lambda: True
        self.register_callback = lambda: True
        self._client = etcd3.client(host=self._etcd_host,
                            port=self._etcd_port)        
        self._leader_election_enabled = leader_election_enabled
        self._registration_enabled = registration_enabled                
        if self._registration_enabled:
            self._stop = stop_event        
            self._thread = threading.Thread(target=self._run, daemon = True)
            self._service_client = etcd3.client(host=self._etcd_host,
                            port=self._etcd_port)        
            if not self._stop:
                raise Exception("Stop event is mandatory if registration is enabled")
            
    def start(self):
        serv_dir = combine_path([self.root, "services"])
        self._mkdir(self._service_client, serv_dir)
        self._thread.start()        

    def stop(self):
        self._stop.set()    

    def _put_not_exist(self, client, key, value, lease=None):
        status, _ = client.transaction(
            compare=[
                client.transactions.version(key) == 0
            ],
            success=[
                client.transactions.put(key, value, lease)
            ],
            failure=[],
        )
        return status


    def _leader_election(self):
        lease = None
        value = simpleProducer.value_serializer({
            "id" : self._id,
            "election_time" : datetime.datetime.now()
        })
        try:
            lease = self._service_client.lease(DEFAULT_LEASE_TTL)
            if self._leader_election_enabled:
                status = self._put_not_exist(self._service_client, self.leader_key, value, lease)
            else:
                status = True
        except Exception as ex:
            logging.debug(ex) 
            trace = traceback.format_exc() 
            logging.debug(trace)
            status = False
        return status, lease

    def _mkdir(self, client, path, ephemeral=False, lease=None):
        if ephemeral:
            lease = self._register_lease
        parts = path.split("/")
        directory = ""
        for part in parts:
            if directory != "":
                directory += "/"    
            directory += part
            self._put_not_exist(client, directory, DIR_VALUE, lease)

    def _register(self):
        if not self._registration_enabled:
            return
        serv_dir = combine_path([self.root, "services", str(self._id)])
        key = combine_path([serv_dir,"id"])
        value = simpleProducer.value_serializer({
            "id" : self._id,
            "version" : version.__version__,
            "start_time" : datetime.datetime.now()
        })
        try:
            lease = self._service_client.lease(DEFAULT_LEASE_TTL)
            self._mkdir(self._service_client, serv_dir, lease=lease)
            self._service_client.put(key, value, lease)
            logging.info('registred {} id: {} v: {}'.format(
                self._processor_type, self._id, version.__version__))
        except Exception as ex:
            logging.debug(ex) 
            trace = traceback.format_exc() 
            logging.debug(trace)
        return lease

    def put_config(self, path, key, value):
        serv_dir = combine_path(["config", path])
        self.put(serv_dir, key, value, ephemeral=False)

    def del_config(self, path, key):
        path = combine_path(["config", path, key])
        self.delete(path)

    def get_config(self, path):
        path = combine_path(["config", path, "/"])
        return self.get(path)

    def put_status(self, path, key, value, lease=None):
        serv_dir = combine_path(["services", str(self._id), path])
        if lease:
            self.put(serv_dir, key, value, lease=lease)
        else:
            self.put(serv_dir, key, value, ephemeral=True)

    def del_status(self, path, key):
        path = combine_path(["services", str(self._id), path, key])
        self.delete(path)

    def get_status(self, path):
        path = combine_path(["services", str(self._id), path, "/"])
        return self.get(path)

    def put(self, path, key, value, ephemeral=True, lease=None):
        if not (self._thread.is_alive() and self._register_lease):
            return False
        path = combine_path([self.root, path])
        key = combine_path([path, key])
        value = simpleProducer.value_serializer(value)

        logging.debug("put {}: {}, ephemeral: {}".format(key, value, ephemeral))

        if ephemeral:
            lease = self._register_lease
        try:
            self._mkdir(self._client, key, ephemeral)
            self._client.put(key, value, lease)
        except Exception as ex:
            logging.debug(ex) 
            trace = traceback.format_exc() 
            logging.debug(trace)
            return False
        return True

    def delete(self, path):
        path = combine_path([self.root, path])
        logging.debug("delete {}".format(path))
        self._client.delete(path)

    def get(self, path):
        path = combine_path([self.root, path])
        logging.debug("get {}".format(path))
        data = self._client.get_prefix(path)
        kv = {}
        metadata = {}
        for datum in data:
            value = deserialize(datum[0])
            if not value:
                continue
            metadatum = datum[1]
            key = metadatum.key.decode("utf-8")
            kv[key] = value
            metadata[key] = metadatum
        logging.debug("got {}".format(str(kv)))
        return kv, metadata

    def _run_work(self, leader, leader_lease=None):
        self._register_lease.refresh()
        self.work_callback(leader)
        
    def _run(self):

        try:
            self._register_lease = self._register()
            self.register_callback()
        except Exception as ex:
            logging.error(ex) 
            trace = traceback.format_exc() 
            logging.debug(trace)
            self._register_lease = None
            return
        
        try:
            while not self._stop.is_set():
                if self._leader_election_enabled:
                    logging.info('leader election {}'.format(self._id))
                leader, lease = self._leader_election()

                if leader:
                    if self._leader_election_enabled:
                        logging.info('leader {}'.format(self._id))
                        self.leader_event.set()
                        self.leader_callback()
                    try:
                        while not self._stop.wait(DEFAULT_SLEEP):
                            lease.refresh()
                            self._run_work(leader=True, leader_lease=lease)
                        return
                    except Exception as ex:
                        logging.error(ex) 
                        trace = traceback.format_exc() 
                        logging.debug(trace)
                        return
                    finally:
                        lease.revoke()
                else:
                    logging.info('follower; standby {}'.format(self._id))

                    election_event = threading.Event()
                    def watch_cb(event):
                        if isinstance(event, etcd3.events.DeleteEvent):
                            election_event.set()
                    watch_id = self._service_client.add_watch_callback(self.leader_key, watch_cb)
                    self.follower_callback()

                    try:
                        while not election_event.is_set():
                            if self._stop.wait(DEFAULT_SLEEP):
                                return
                            self._run_work(leader=False)
                        logging.info('new election {}'.format(self._id))
                    except Exception as ex:
                        logging.error(ex) 
                        trace = traceback.format_exc() 
                        logging.debug(trace)
                        return
                    finally:
                        self._service_client.cancel_watch(watch_id)
        finally:
            if self._register_lease: 
                self._register_lease.revoke()
                self._register_lease = None

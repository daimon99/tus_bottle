# coding: utf-8

import logging
import os
import threading
import time

from fdfs_client import client
from persistqueue import UniqueQ

log = logging.getLogger(__name__)
QUEUE_NAME = '/tmp/FDFS_UPLOAD_QUEUE'

CONF_FILE = os.path.expanduser('~/.local/etc/fdfs/client.conf')


class FdfsUploader(object):
    def __init__(self):
        self.cli = client.Fdfs_client(client.get_tracker_conf(CONF_FILE))
        self.queue = UniqueQ(QUEUE_NAME)

    def add_to_queue(self, local_file_full_path):
        self.queue.put(local_file_full_path)
        self.cli.modify_by_buffer()

    @staticmethod
    def start_thread_listen():
        t1 = threading.Thread(target=listen_thread)
        t1.start()


def listen_thread():
    log.info('Fdfs upload thread start.')
    fdfs_uploader = FdfsUploader()
    while True:
        try:
            file_to_upload = fdfs_uploader.queue.get()
            if os.path.exists(file_to_upload):
                try:
                    print('uploading...')
                    fdfs_uploader.cli.smart_upload_by_filename(file_to_upload)
                    print('uploading ok.')
                    # mark as done
                except:
                    if fdfs_uploader.cli.appender_ret_obj:
                        remote_file_id = fdfs_uploader.cli.appender_ret_obj.get('Remote file_id')
                        print('remote file id', remote_file_id)
                        if remote_file_id:
                            log.warning('Delete fail upload file id: %s', remote_file_id)
                            fdfs_uploader.cli.delete_file(remote_file_id)
                    raise
            else:
                log.warning('file not exist: %s', file_to_upload)
        except Exception as e:
            log.exception('fdfs uploader listen error here. retrying after 10s.')
            time.sleep(10)

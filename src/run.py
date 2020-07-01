# coding: utf-8
import base64
import hashlib
import json
import os
import shutil
import time
import uuid
from operator import itemgetter
from pathlib import Path
from wsgiref.handlers import format_date_time

from bottle import run, route, request, response, abort, static_file, hook

from fdfsupload import FdfsUploader

UPLOAD_HOME = '/tmp'
MAX_UPLOAD_SIZE = 1024 * 1024 * 1024 * 10
BASE_DIR = os.path.dirname(__file__)

TUS_UPLOAD_OFFSET = 'Upload-Offset'
TUS_UPLOAD_LENGTH = 'Upload-Length'
TUS_VERSION = 'Tus-Version'
TUS_RESUMABLE = 'Tus-Resumable'
TUS_EXTENSION = 'Tus-Extension'
TUS_MAX_SIZE = 'Tus-Max-Size'
TUS_X_HTTP_METHOD_OVERRIDE = 'X-HTTP-Method-Override'
TUS_UPLOAD_METADATA = 'Upload-Metadata'
TUS_UPLOAD_DEFER_LENGTH = 'Upload-Defer-Length'
TUS_UPLOAD_EXPIRES = 'Upload-Expires'
TUS_TUS_CHECKSUM_ALGORITHM = 'Tus-Checksum-Algorithm'
TUS_UPLOAD_CHECKSUM = 'Upload-Checksum'
TUS_UPLOAD_CONCAT = 'Upload-Concat'

"""
TODO:

These feature need tobe impl.

> https://tus.io/protocols/

1. creation-defer-length
2. creation-with-upload
3. concatenation

"""

fdfs_uploader = FdfsUploader()


@hook('after_request')
def common_tus_headers():
    response.set_header(TUS_RESUMABLE, '1.0.0')
    response.set_header('Cache-Control', 'no-store')
    response.set_header(TUS_VERSION, '1.0.0,0.2.2,0.2.1')
    response.set_header(TUS_MAX_SIZE, MAX_UPLOAD_SIZE)  # max 20G
    response.set_header(TUS_EXTENSION, 'creation,expiration,expiration,termination,checksum')


@route('/ping')
def ping():
    return 'pong'


@route('/')
def do_test():
    return static_file('uppy.html', BASE_DIR)


@route('/upload', method='POST')
def do_normal_upload():
    upload = request.files.get('upload')
    folder_id = uuid.uuid4().hex
    folder_path = get_tmp_folder(folder_id)
    os.mkdir(folder_path)
    upload.save(os.path.join(folder_path, upload.filename))
    return 'ok'


@route('/tus-upload/<folder>', method='GET')
def do_head(folder):
    """
    The Server MUST always include the Upload-Offset header in the response for a HEAD request,
    even if the offset is 0, or the upload is already considered completed.
    If the size of the upload is known, the Server MUST include the Upload-Length header in the response.
    If the resource is not found, the Server SHOULD return either the 404 Not Found, 410 Gone
    or 403 Forbidden status without the Upload-Offset header.

    The Server MUST prevent the client and/or proxies from caching the response
    by adding the Cache-Control: no-store header to the response.
    :param folder:
    :return:
    """
    tmp_folder = get_tmp_folder(folder)
    if not os.path.exists(tmp_folder):
        return abort(404)
    offset = get_folder_size(tmp_folder)
    response.set_header(TUS_UPLOAD_OFFSET, offset)
    response.set_header(TUS_UPLOAD_LENGTH, offset)


@route('/tus-upload/<folder>', method='PATCH')
def do_patch(folder):
    """
    The Server SHOULD accept PATCH requests against any upload URL and apply the bytes contained in the message at
    the given offset specified by the Upload-Offset header.

    All PATCH requests MUST use Content-Type: application/offset+octet-stream, otherwise the server SHOULD return a
    415 Unsupported Media Type status.

    The Upload-Offset header’s value MUST be equal to the current offset of the resource. In order to achieve parallel
    upload the Concatenation extension MAY be used. If the offsets do not match, the Server MUST respond with the 409
    Conflict status without modifying the upload resource.

    The Client SHOULD send all the remaining bytes of an upload in a single PATCH request, but MAY also use multiple
    small requests successively for scenarios where this is desirable. One example for these situations is when the
    Checksum extension is used.

    The Server MUST acknowledge successful PATCH requests with the 204 No Content status. It MUST include the
    Upload-Offset header containing the new offset. The new offset MUST be the sum of the offset before the PATCH
    request and the number of bytes received and processed or stored during the current PATCH request.

    If the server receives a PATCH request against a non-existent resource it SHOULD return a 404 Not Found status.

    Both Client and Server, SHOULD attempt to detect and handle network errors predictably. They MAY do so by
    checking for read/write socket errors, as well as setting read/write timeouts. A timeout SHOULD be handled by
    closing the underlying connection.

    The Server SHOULD always attempt to store as much of the received data as possible.
    :param folder:
    :return:
    """
    content_type = request.content_type
    if content_type != 'application/offset+octet-stream':
        abort(415)
    content_length = int(request.content_length)
    upload_offset = int(request.get_header(TUS_UPLOAD_OFFSET))
    file_path = get_tmp_folder(f'{folder}/{upload_offset}_{content_length}.part')
    body = request.body.read()
    client_checksum = request.get_header('Upload-Checksum')
    if client_checksum:
        client_alg: str
        client_alg, client_crc = client_checksum.split(' ')
        client_crc = base64.b64decode(client_crc)
        crc = None
        if client_alg.lower() == 'md5':
            crc = hashlib.md5(body).digest()
        elif client_alg.lower() == 'sha1':
            crc = hashlib.sha1(body).digest()
        else:
            abort(400, f'Bad Request')
        if client_crc != crc:
            abort(460, 'Checksum Mismatch')

    with open(file_path, 'wb') as fout:
        fout.write(body)

    response.set_header(TUS_UPLOAD_OFFSET, upload_offset + content_length)
    set_expire_header()
    response.status = 204
    check_complete_and_combine(folder)


@route('/tus-upload/<folder>', method='DELETE')
def do_delete(folder):
    folder_path = get_tmp_folder(folder)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
        response.status = 204
        return
    else:
        abort(404)


@route('/tus-upload/', method='OPTIONS')
def do_options():
    """
    An OPTIONS request MAY be used to gather information about the Server’s current configuration. A successful
    response indicated by the 204 No Content or 200 OK status MUST contain the Tus-Version header. It MAY include the
    Tus-Extension and Tus-Max-Size headers.

    The Client SHOULD NOT include the Tus-Resumable header in the request and the Server MUST ignore the header.

    :return:

        HTTP/1.1 204 No Content
        Tus-Resumable: 1.0.0
        Tus-Version: 1.0.0,0.2.2,0.2.1
        Tus-Max-Size: 1073741824
        Tus-Extension: creation,expiration
    """
    response.set_header(TUS_TUS_CHECKSUM_ALGORITHM, 'sha1 md5')
    response.status = 204


@route('/tus-upload', method='POST')
def do_creation():
    """
    Creation

    The Client and the Server SHOULD implement the upload creation extension.
    If the Server supports this extension, it MUST add creation to the Tus-Extension header.
    """
    upload_defer_length = request.get_header(TUS_UPLOAD_DEFER_LENGTH)
    if upload_defer_length and upload_defer_length != '1':
        abort(400)
    upload_length = request.get_header(TUS_UPLOAD_LENGTH)
    upload_length = int(upload_length) if upload_length and upload_length.isnumeric() else 0

    if upload_length > MAX_UPLOAD_SIZE:
        abort(413)

    upload_metadata: str = request.get_header(TUS_UPLOAD_METADATA)
    meta = {
        'upload_length': upload_length
    }
    if upload_metadata:
        meta.update(convert_meta_to_json(upload_metadata))
    location = uuid.uuid4().hex
    location_in_disk = get_tmp_folder(location)
    os.mkdir(location_in_disk)

    with open(os.path.join(location_in_disk, 'meta.json'), 'w') as meta_out:
        json.dump(meta, meta_out, ensure_ascii=False, indent=2)

    response.set_header('Location', f'/tus-upload/{location}')
    set_expire_header()
    response.status = 201


def get_folder_size(folder):
    root_directory = Path(folder)
    size = sum(f.stat().st_size for f in root_directory.glob('*.part') if f.is_file())
    return size


def get_tmp_folder(folder):
    return os.path.join(UPLOAD_HOME, folder)


def convert_meta_to_json(metadata_str: str):
    meta = {}
    for item in metadata_str.split(','):
        k, y = item.split(' ')
        meta[k] = base64.b64decode(y).decode()
    return meta


def check_complete_and_combine(folder_id):
    folder_path = get_tmp_folder(folder_id)
    if not os.path.exists(folder_path):
        return
    meta_file_path = os.path.join(folder_path, 'meta.json')
    if not os.path.exists(meta_file_path):
        return
    with open(meta_file_path) as meta_in:
        meta = json.load(meta_in)
    upload_length = meta.get('upload_length')
    size = get_folder_size(folder_path)
    if size != upload_length:
        return
    file_name = meta.get('filename')
    if not file_name:
        file_name = folder_id
    all_files = Path(folder_path).glob('*.part')
    all_files_list = [[x.absolute(), int(str(x.name).split('_', 1)[0])] for x in all_files]
    all_files_list = sorted(all_files_list, key=itemgetter(1))
    buffer_size = 1024 * 1024
    target_file_name = os.path.join(folder_path, file_name)
    # todo 效率太低了。应该小文件随时传，不合并。
    with open(target_file_name, 'wb') as fout:
        print('start combining files.')
        for _file in all_files_list:
            with open(_file[0], 'rb') as fin:
                while True:
                    data = fin.read(buffer_size)
                    if data:
                        fout.write(data)
                    else:
                        break
        print('combine ok now', target_file_name)
        for _file in all_files_list:
            _file[0].unlink()

        fdfs_uploader.add_to_queue(target_file_name)


def set_expire_header():
    expires_on = format_date_time(time.time() + 3600 * 24)  # 一天后过期
    response.set_header(TUS_UPLOAD_EXPIRES, expires_on)


if __name__ == '__main__':
    fdfs_uploader.start_thread_listen()
    run(host='127.0.0.1', port=8080, reloader=True)

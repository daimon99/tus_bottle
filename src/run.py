# coding: utf-8
import base64
import json
import os
import uuid

from bottle import run, route, request, response, abort, static_file

UPLOAD_HOME = '/tmp'
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


@route('/ping')
def ping():
    return 'pong'


@route('/')
def do_test():
    return static_file('uppy.html', BASE_DIR)


@route('/upload/<folder>', method='GET')
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
    response.set_header(TUS_RESUMABLE, '1.0.0')
    response.set_header('Cache-Control', 'no-store')


@route('/upload/<folder>', method='PATCH')
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
    with open(file_path, 'wb') as fout:
        fout.write(request.body.read())
    print('content_length', content_length, upload_offset)
    response.set_header(TUS_UPLOAD_OFFSET, upload_offset + content_length)
    response.status = 204


@route('/upload/', method='OPTIONS')
def do_options():
    """

    :return:

        HTTP/1.1 204 No Content
        Tus-Resumable: 1.0.0
        Tus-Version: 1.0.0,0.2.2,0.2.1
        Tus-Max-Size: 1073741824
        Tus-Extension: creation,expiration
    """
    response.set_header(TUS_RESUMABLE, '1.0.0')
    response.set_header(TUS_VERSION, '1.0.0,0.2.2,0.2.1')
    response.set_header(TUS_MAX_SIZE, 1024 * 1024 * 1024 * 10)  # max 20G
    response.set_header(TUS_EXTENSION, 'creation,expiration')
    response.status = 204


@route('/upload', method='POST')
def do_creation():
    """
    Creation

    The Client and the Server SHOULD implement the upload creation extension.
    If the Server supports this extension, it MUST add creation to the Tus-Extension header.
    """
    print('do_creation')
    upload_metadata: str = request.get_header(TUS_UPLOAD_METADATA)
    upload_length = request.get_header(TUS_UPLOAD_LENGTH)
    upload_length = int(upload_length) if upload_length and upload_length.isnumeric() else 0
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
    response.set_header('Location', f'/upload/{location}')
    response.set_header(TUS_RESUMABLE, '1.0.0')
    response.set_header('Cache-Control', 'no-store')
    return


def get_folder_size(folder):
    from pathlib import Path
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


if __name__ == '__main__':
    run(host='127.0.0.1', port=8080, reloader=True)

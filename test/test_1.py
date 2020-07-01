# coding: utf-8

def test_1():
    from tusclient import client
    my_client = client.TusClient('http://localhost:8080/upload')
    uploader = my_client.uploader('testfile', chunk_size=200000)
    uploader.upload()

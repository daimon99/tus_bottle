# coding: utf-8


def test_2():
    from fdfs_client import client
    cli = client.Fdfs_client(client.get_tracker_conf("~/.local/etc/fdfs/client.conf"))
    cli.upload_appender_by_buffer(b'a', '.test')

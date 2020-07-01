基于 Bottle 框架的 TUS 协议实现
===============================

说明
------

基于 `Bottle <https://bottlepy.org/docs/dev/>`_ 框架的 `TUS 协议 <https://tus.io/protocols/resumable-upload.html>`_ 实现。

同时集成了 `FastDFS <https://github.com/happyfish100/fastdfs>`_ 上传。

tus 上传文件后，先落地存储到tus 上，再把文件放到Queue 中，之后通过队列慢慢再把文件分散存储到 dfs 服务器上。

先落地存一下的原因，是因为公网云服务器的下行流量不限速，但上行流量限速，因此最快速度先把文件落下来。再慢慢回传到dfs 服务器。

这样可以有效利用服务器带宽。

可以类似这样搭个服务器集群::

    示意图
         ┌------------------------------------------------------------------------------------┐
         |                                     NGINX PROXY AND BALANCE                        |
         └------------------------------------------------------------------------------------┘
                \/                  \/                   \/                         ^
                \/                  \/                   \/                         ^
                \/                  \/                   \/                         ^
         ┌--------------┐    ┌----------------┐   ┌--------------┐      ┌---------------------┐
         | TUS SERVER 1 |    | TUS SERVER 2   |   | TUS SERVER 3 |      |  Web server cluster |
         |     FRPS-1   |    |      FRPS-2    |   |     FRPS-3   |      |         FRPS-4      |
     /|\ └--------------┘    └----------------┘   └--------------┘      └---------------------┘
      | Cloud    |                   |                     |                        ^
    ----------   └----┐              |             ┌-------┘                        ^
      | Home          |              |             |                                ^
     \|/             \|/            \|/           \|/                               ^
                  ┌-----------------------------------------┐                       ^
                  |   FRPC-1  |    FRPC-2       | FRPC-3    |                       ^
                  |      FDFS SERVER CLUSTER    | FRPC-4    |  --------->>>---------┘
                  └-----------------------------------------┘

其中 FDFS cluster 可以放在家里。
这样 Tus server 的 upload 流量，可以全部用来给 fdfs 上传使用

客户端要访问文件时，通过另外的 web server 访问。

这样，基本可以用非常廉价的成本，来搭建一个私有网盘。用上了以下优势资源：

* 家庭网关的廉价存储、计算与带宽资源
* 公网云服务器的 IP 与 80/443 端口的垄断资源
* 公网云服务器上行流量收费极贵，下行流量免费

环境
------

1. python3.6 以上
2. linux or mac

安装
------

.. code-block::

    git clone https://github.com/daimon99/tus_bottle
    cd tus_bottle
    pip install -r requirements.txt
    mkdir -p ~/.local/etc/fdfs/

之后，请把 ``fdfs`` 的配置文件 ``client.conf`` 放在 ``.local/etc/fdfs`` 目录下。
如果不使用 fdfs 上传到文件服务器集群，请自己注释掉相关实现

* ``run.py/check_complete_and_combine`` 最后的队列发起部分
* ``__main__`` 中的 ``fdfs_uploader.start_thread_listen()``

使用
--------

.. code-block::

    cd tus_bottle
    python3 run.py

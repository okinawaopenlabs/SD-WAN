# Open SD-WAN
集中分散協調型アーキテクチャの SD-WAN PoC

![image1](https://user-images.githubusercontent.com/13248874/68669223-5ef71480-058d-11ea-8694-18d37b7a9bbf.png)

■機器前提条件(中央コントローラ/CPE共通)

 ●OSは，Ubuntu 14.04.x であること


■中央コントローラ構築

 ●ローカルコントローラ用のライブラリインストール
	  
	  sudo apt-get install python-lxml python-setuptools unzip python-dev libmysqlclient-dev
	  sudo easy_install -U pip
	  sudo pip install -U setuptools oslo.config msgpack-python eventlet routes webob MySQL-python flask peewee unirest networkx kafka

#環境によっては以下必要になる可能性あり
	
	export LC_ALL=en_US.UTF-8
	export LANG=en_US.UTF-8
	
 ●ryuインストール

	cd /Applicationryu-lagopus-ext-lagopus-general-tunnel-ext
	sudo python setup.py install

●OpenSD-WAN用のDB作成

		mysql -u root -p <mysql_Password>
		create database Open-SD-WAN;
		exit

●中央コントローラ用のスキーマ登録

		mysql -u root -p Open-SD-WAN < /Database/CenterController_BaseSQL.sql

●中央コントローラーの配備













■CPE構築

●Lanner FW-7551へのUbuntuセットアップ

https://github.com/jorgebonilla/Lanner_FW7551d_Ubuntu  
http://www.bosco-tech.com/ubuntu_lanner/  
を参考に

●ライブラリのインストール

 ・ローカルコントローラ用

	sudo apt-get install python-lxml python-setuptools unzip python-dev libmysqlclient-dev
	sudo easy_install -U pip
	sudo pip install -U setuptools oslo.config msgpack-python eventlet routes webob MySQL-python flask peewee unirest networkx kafka

#環境によっては以下必要になる可能性あり

	export LC_ALL=en_US.UTF-8
	export LANG=en_US.UTF-8

・lagopus用

	sudo apt-get install git libgmp-dev libssl-dev libpcap-dev flex bison make

●hugepages設定

	$ sudo nano /etc/default/grub
	 GRUB_CMDLINE_LINUX="hugepages=1024" #追記/修正
	$ update-grub

	$ mkdir /mnt/huge
	$ sudo nano /etc/fstab
	nodev /mnt/huge hugetlbfs defaults 0 0 #最下部に追記
		$ sudo shutdown -r now

●ryuインストール
	
	cd /Application/ryu-lagopus-ext-lagopus-general-tunnel-ext
	sudo python setup.py install

●Lagopusインストール

	cd /Application/lagopus
	sudo ./configure --enable-jumbo-frame

#DPDK不要の場合は --enable-jumboの後ろに --disable-dpdkを追記

	make
	sudo make install

●Lagopus設定
https://github.com/lagopus/lagopus/blob/master/misc/examples/lagopus.dsl  
を参考に /usr/local/etc/lagopus/lagopus.dsl を作成

●OpenSD-WAN用のDB作成

	mysql -u root -p <mysql_Password>
	create database Open-SD-WAN;
	exit

●CPE用のスキーマ登録

		mysql -u root -p Open-SD-WAN < /Database/CPE_BaseSQL.sql

●ローカルコントローラの配備

		cd /Application/opensdwan
		sudo nano edge.py
			 ####設定セット####
			 CenterController_IPAddress = "<中央コントローラのIPに置換>"
			 Kafka_IPAddress = "<KafkaのIPに置換>"
			 #####ここまで#####


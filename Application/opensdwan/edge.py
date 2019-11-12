# -*- coding: utf-8 -*-
####設定セット####
CenterController_IPAddress = "192.168.26.150"
Kafka_IPAddress = "192.168.26.151"
ArpReply_Vlan=3021
#####ここまで#####

# -*- coding: utf-8 -*-
#コントローラライブラリセット
from ryu.base.app_manager import RyuApp
from ryu.controller.ofp_event import EventOFPSwitchFeatures
from ryu.controller.ofp_event import EventOFPPacketIn
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.ofproto import ofproto_v1_3
from ryu.ofproto.ofproto_v1_3 import OFP_VERSION

#パケット生成
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp
from ryu.lib.packet import ipv4
from ryu.lib.packet import cfm
from ryu.lib.packet import vlan
from ryu.lib.packet import icmp
from ryu.ofproto import inet
from ryu.ofproto import ether

#Mysql接続
import MySQLdb
import MySQLdb.cursors

#API
#from flask import Flask, jsonify, abort, make_response
from flask import request, url_for,jsonify, abort, make_response
from flask_api import FlaskAPI, status, exceptions
import requests
import json

from pprint import pprint

#時刻処理
import pytz
from pytz import timezone
import time
import datetime
from datetime import datetime
import datetime as dt

#マルチスレッド用
import threading
from threading import Thread, BoundedSemaphore
from Queue import Queue

#抽象構文木
import ast

#Kafka
from kafka import KafkaConsumer, KafkaProducer

#経路探索
import networkx as nx
from itertools import islice

#その他
import array
import netaddr
import unirest

#グローバル変数
api = FlaskAPI(__name__)
dpid_list={}
my_dpid=0
portdata={}
Master_Controller_URL = "http://"+ CenterController_IPAddress +":3000"


#OAMパケット管理配列
oam = {}
oam["cc"] = {}
oam["lb"] = {}

#スレッド管理
lock = threading.RLock()
smp = threading.Semaphore(1000)

producer = KafkaProducer(bootstrap_servers=Kafka_IPAddress+':9092')

class Open_SDWAN(RyuApp,threading.Thread):
	OFP_VERSIONS = [OFP_VERSION]

	def __init__(self, *args, **kwargs):
		super(Open_SDWAN, self).__init__(*args, **kwargs)

	@set_ev_cls(EventOFPSwitchFeatures, CONFIG_DISPATCHER)
	def switch_features_handler(self, ev):
		global my_dpid
		datapath = ev.msg.datapath
		ofp = datapath.ofproto
		ofp_parser = datapath.ofproto_parser

		#DPIDをDBに登録
		dpid_list[int(datapath.id)] = datapath
		my_dpid = datapath.id
		dinfo = {}

		self.install_flow(datapath)
		#接続ログ書き出し
		self.logger.info('installing flow@'+str(datapath.id))

	#SQL実行
	def send_sql(self,sql,con_type):
		if con_type == "center":
			dbaddr = "192.168.26.150"
		else:
			dbaddr = "127.0.0.1"

		sqlbase = MySQLdb.connect(host=dbaddr,db="Open-SD-WAN",user="root",passwd="Openlab0508",charset="utf8",cursorclass=MySQLdb.cursors.DictCursor)
		sqlcon = sqlbase.cursor()
		sqlcon.execute(sql)
		sqlbase.commit()
		result = sqlcon.fetchall()
		sqlcon.close()
		sqlbase.close()
		return result


	def install_flow(self, datapath):
		ofp = datapath.ofproto
		ofp_parser = datapath.ofproto_parser

		#フロー初期化
		match = ofp_parser.OFPMatch()
		dinfo={}
		dinfo["mode"]="delete_flow"
		dinfo["priority"]=400
		self.insert_flow(datapath,match,dinfo)

		#ARPパケインフロー追加
		match = ofp_parser.OFPMatch(ip_proto=17,eth_type=2048,udp_src=10)
		dinfo["mode"] = "other"
		dinfo["out_port"] = ofproto_v1_3.OFPP_CONTROLLER
		dinfo["priority"] = 1
		result = self.insert_flow(datapath,match,dinfo)

		#ARPパケインフロー追加
		match = ofp_parser.OFPMatch(eth_type=2054)
		dinfo["mode"] = "other"
		dinfo["out_port"] = ofproto_v1_3.OFPP_CONTROLLER
		dinfo["priority"] = 1
		result = self.insert_flow(datapath,match,dinfo)


		match = ofp_parser.OFPMatch(eth_type=2048,ip_proto=1)
		dinfo["mode"] = "other"
		dinfo["out_port"] = ofproto_v1_3.OFPP_CONTROLLER
		dinfo["priority"] = 1
		result = self.insert_flow(datapath,match,dinfo)

		#既存のフロー追加
		sql = "select * from flow_table"
		result = self.send_sql(sql,"local")
		num = 0
		while num < len(result):
			dinfo = ast.literal_eval(result[num]["actions"])
			match = ast.literal_eval(result[num]["flow_match"].replace('OFPMatch(oxm_fields=','').replace(')',''))
			match = ofp_parser.OFPMatch(**match)
			self.insert_flow(datapath,match,dinfo)
			num+=1

	def insert_flow(self,datapath,match,dinfo):
		ofp = datapath.ofproto
		ofp_parser = datapath.ofproto_parser
		cookie = cookie_mask = 0
		table_id = 0
		idle_timeout = hard_timeout = 0
		buffer_id = ofp.OFP_NO_BUFFER
		priority = dinfo["priority"]
		print dinfo["mode"]
		#VXLAN Decap Edge
		if dinfo["mode"] == "decap":
			actions = [
						ofp_parser.OFPActionPopVlan(ether.ETH_TYPE_8021Q),
						ofp_parser.OFPActionDecap(cur_pkt_type=0, new_pkt_type=67584),
						ofp_parser.OFPActionDecap(cur_pkt_type=67584, new_pkt_type=131089),
						ofp_parser.OFPActionDecap(cur_pkt_type=131089, new_pkt_type=201397),
						ofp_parser.OFPActionDecap(cur_pkt_type=201397, new_pkt_type=0),
						ofp_parser.OFPActionOutput(dinfo["out_port"])
					]

			inst = [ofp_parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,actions)]
			req = ofp_parser.OFPFlowMod(datapath, cookie, cookie_mask,
						table_id, ofp.OFPFC_ADD,
						idle_timeout, hard_timeout,
						priority, buffer_id,
						ofp.OFPP_ANY, ofp.OFPG_ANY,
						ofp.OFPFF_SEND_FLOW_REM,
						match, inst)

		elif dinfo["mode"] == "other":
			actions = [
						ofp_parser.OFPActionPopVlan(ether.ETH_TYPE_8021Q),
						ofp_parser.OFPActionOutput(dinfo["out_port"])
					]

			inst = [ofp_parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,actions)]
			req = ofp_parser.OFPFlowMod(datapath, cookie, cookie_mask,
						table_id, ofp.OFPFC_ADD,
						idle_timeout, hard_timeout,
						priority, buffer_id,
						ofp.OFPP_ANY, ofp.OFPG_ANY,
						ofp.OFPFF_SEND_FLOW_REM,
						match, inst)
		elif dinfo["mode"] == "delete_flow":
			inst = []
			req = ofp_parser.OFPFlowMod(datapath, cookie, cookie_mask,
						table_id, ofp.OFPFC_DELETE,
						idle_timeout, hard_timeout,
						priority, buffer_id,
						ofp.OFPP_ANY, ofp.OFPG_ANY,
						ofp.OFPFF_SEND_FLOW_REM,
						match, inst)
		elif dinfo["mode"] == "encap":
			print "encap"
			encap_vlan =datapath.ofproto_parser.OFPMatchField.make(ofp.OXM_OF_VLAN_VID,dinfo["vlan"])
			actions = [
						ofp_parser.OFPActionEncap(201397),
						ofp_parser.OFPActionSetField(vxlan_vni=dinfo["vni"]),
						ofp_parser.OFPActionEncap(131089),
						ofp_parser.OFPActionSetField(udp_src=1),
						ofp_parser.OFPActionSetField(udp_dst=4789),
						ofp_parser.OFPActionEncap(67584),
						ofp_parser.OFPActionSetField(ipv4_dst=dinfo["to_ip"]),
						ofp_parser.OFPActionSetField(ipv4_src=dinfo["from_ip"]),
						ofp_parser.OFPActionSetNwTtl(64),
						ofp_parser.OFPActionEncap(0),
						ofp_parser.OFPActionSetField(eth_dst=dinfo["to_mac"]),
						ofp_parser.OFPActionSetField(eth_src=dinfo["from_mac"]),
						ofp_parser.OFPActionPushVlan(ether.ETH_TYPE_8021Q),
						ofp_parser.OFPActionSetField(encap_vlan),
						ofp_parser.OFPActionOutput(dinfo["out_port"])
					]
			inst = [ofp_parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,actions)]
			req = ofp_parser.OFPFlowMod(datapath, cookie, cookie_mask,
						table_id, ofp.OFPFC_ADD,
						idle_timeout, hard_timeout,
						priority, buffer_id,
						ofp.OFPP_ANY, ofp.OFPG_ANY,
						ofp.OFPFF_SEND_FLOW_REM,
						match, inst)

		#VXLAN Throw Edge
		elif dinfo["mode"]  == "throw":
			encap_vlan =datapath.ofproto_parser.OFPMatchField.make(ofp.OXM_OF_VLAN_VID,dinfo["vlan"])
			actions = [
						ofp_parser.OFPActionPopVlan(ether.ETH_TYPE_8021Q),
						ofp_parser.OFPActionDecap(cur_pkt_type=0, new_pkt_type=67584),
						ofp_parser.OFPActionSetField(ipv4_dst=dinfo["to_ip"]),
						ofp_parser.OFPActionSetField(ipv4_src=dinfo["from_ip"]),
						ofp_parser.OFPActionSetNwTtl(64),
						ofp_parser.OFPActionEncap(0),
						ofp_parser.OFPActionSetField(eth_dst=dinfo["to_mac"]),
						ofp_parser.OFPActionSetField(eth_src=dinfo["from_mac"]),
						ofp_parser.OFPActionPushVlan(ether.ETH_TYPE_8021Q),
						ofp_parser.OFPActionSetField(encap_vlan),
						ofp_parser.OFPActionOutput(dinfo["out_port"])
					]
			inst = [ofp_parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,actions)]
			req = ofp_parser.OFPFlowMod(datapath, cookie, cookie_mask,
						table_id, ofp.OFPFC_ADD,
						idle_timeout, hard_timeout,
						priority, buffer_id,
						ofp.OFPP_ANY, ofp.OFPG_ANY,
						ofp.OFPFF_SEND_FLOW_REM,
						match, inst)

		elif dinfo["mode"] == "recap":
			print "recap"
			encap_vlan =datapath.ofproto_parser.OFPMatchField.make(ofp.OXM_OF_VLAN_VID,dinfo["vlan"])
			actions = [
						ofp_parser.OFPActionPopVlan(ether.ETH_TYPE_8021Q),
						ofp_parser.OFPActionDecap(cur_pkt_type=0, new_pkt_type=67584),
						ofp_parser.OFPActionDecap(cur_pkt_type=67584, new_pkt_type=131089),
						ofp_parser.OFPActionDecap(cur_pkt_type=131089, new_pkt_type=201397),
						ofp_parser.OFPActionDecap(cur_pkt_type=201397, new_pkt_type=0),
						ofp_parser.OFPActionEncap(201397),
						ofp_parser.OFPActionSetField(vxlan_vni=dinfo["vni"]),
						ofp_parser.OFPActionEncap(131089),
						ofp_parser.OFPActionSetField(udp_src=dinfo["sport"]),
						ofp_parser.OFPActionSetField(udp_dst=dinfo["dport"]),
						ofp_parser.OFPActionEncap(67584),
						ofp_parser.OFPActionSetField(ipv4_dst=dinfo["to_ip"]),
						ofp_parser.OFPActionSetField(ipv4_src=dinfo["from_ip"]),
						ofp_parser.OFPActionSetNwTtl(64),
						ofp_parser.OFPActionEncap(0),
						ofp_parser.OFPActionSetField(eth_dst=dinfo["to_mac"]),
						ofp_parser.OFPActionSetField(eth_src=dinfo["from_mac"]),
						ofp_parser.OFPActionPushVlan(ether.ETH_TYPE_8021Q),
						ofp_parser.OFPActionSetField(encap_vlan),
						ofp_parser.OFPActionOutput(dinfo["out_port"])
					]
			inst = [ofp_parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,actions)]
			req = ofp_parser.OFPFlowMod(datapath, cookie, cookie_mask,
						table_id, ofp.OFPFC_ADD,
						idle_timeout, hard_timeout,
						priority, buffer_id,
						ofp.OFPP_ANY, ofp.OFPG_ANY,
						ofp.OFPFF_SEND_FLOW_REM,
						match, inst)

		datapath.send_msg(req)
		return 0

	#パケイン後の処理
	@set_ev_cls(EventOFPPacketIn, MAIN_DISPATCHER)
	def _packet_in_handler(self, ev):
		receive_time = datetime.now().strftime("%Y/%m/%d %H-%M-%S.%f")
		t = Proceed_PKT_IN(ev,receive_time)
		t.start()
		return True

	def ChangeRoute(self,vni):
		global dpid_list
		global Master_Controller_URL
		sql = u"select * from flow_table where vni="+str(vni)
		result = self.send_sql(sql,"local")

		if len(result) != 0:
			if dpid_list.has_key(int(result[0]["dpid"]))==True:
				datapath = dpid_list[int(result[0]["dpid"])]
				ofp = datapath.ofproto
				ofp_parser = datapath.ofproto_parser
				if result[0]["category"] == "Primary":
					try:
						pri_sql = u"select * from flow_table where category='Primary' and start="+str(result[0]["end"])+" and end="+str(result[0]["start"])
						pri_result = self.send_sql(pri_sql,"local")
					except:
						pass

					try:
						sec_sql = u"select * from flow_table where category='Secondary' and start="+str(result[0]["end"])+" and end="+str(result[0]["start"])
						sec_result = self.send_sql(sec_sql,"local")
					except:
						pass

					try:
						rec_pri_sql = u"select * from flow_table where category='Primary' and start="+str(result[0]["start"])+" and end="+str(result[0]["end"])
						rec_pri_result = self.send_sql(rec_pri_sql,"local")
					except:
						pass

					try:
						rec_sec_sql = u"select * from flow_table where category='Secondary' and start="+str(result[0]["start"])+" and end="+str(result[0]["end"])
						rec_sec_result = self.send_sql(rec_sec_sql,"local")
					except:
						pass

					#SecondaryRouteの優先度上昇
					try:
						match = ast.literal_eval(sec_result[0]["flow_match"].replace('OFPMatch(oxm_fields=','').replace(')',''))
						match = ofp_parser.OFPMatch(**match)
						dinfo = ast.literal_eval(sec_result[0]["actions"])
						dinfo["priority"] = 400
						change_pri_result = self.insert_flow(datapath,match,dinfo)
					except:
						pass

					try:
						sec_sql = u"update flow_table set actions=\"" + str(dinfo) +"\",category=\"Primary\" where vni=" + str(sec_result[0]["vni"]) + " and dpid="+str(result[0]["dpid"])
						sec_result = self.send_sql(sec_sql,"local")
						receive_url = str(Master_Controller_URL)+"/sql/" + str(sec_sql)
						receive_result = requests.get(receive_url)
					except:
						pass

					try:
						sec_sql = u"update flow_table set category=\"Primary\" where vni=" + str(rec_sec_result[0]["vni"]) + " and dpid="+str(result[0]["dpid"])
						sec_result = self.send_sql(sec_sql,"local")
						receive_url = str(Master_Controller_URL)+"/sql/" + str(sec_sql)
						receive_result = requests.get(receive_url)
					except:
						pass

					try:
						#PrimaryRouteの優先度をSecondaryRouteの値に修正
						match = ast.literal_eval(pri_result[0]["flow_match"].replace('OFPMatch(oxm_fields=','').replace(')',''))
						match = ofp_parser.OFPMatch(**match)
						dinfo = ast.literal_eval(pri_result[0]["actions"])
						dinfo["priority"] = 300
						change_pri_ = self.insert_flow(datapath,match,dinfo)
					except:
						pass

					try:
						pri_sql = u"update flow_table set actions=\"" + str(dinfo) +"\",category=\"Secondary\" where vni=" + str(pri_result[0]["vni"]) + " and dpid="+str(result[0]["dpid"])
						pri_result = self.send_sql(pri_sql,"local")
						receive_url = str(Master_Controller_URL)+"/sql/" + str(pri_sql)
						receive_result = requests.get(receive_url)
					except:
						pass

					try:
						pri_sql = u"update flow_table set category=\"Secondary\" where vni=" + str(rec_pri_result[0]["vni"]) + " and dpid="+str(result[0]["dpid"])
						pri_result = self.send_sql(pri_sql,"local")

						receive_url = str(Master_Controller_URL)+"/sql/" + str(pri_sql)
						receive_result = requests.get(receive_url)
					except:
						pass

		return 0

	def Request_ChangeRoute(self,vni):
		global dinfo
		global my_dpid
		global dpid_list

		#断経路検索
		sql = u"select * from flow_table where vni="+str(vni)
		vni_result = self.send_sql(sql,"local")

		#終始点検索
		start=vni_result[0]["start"]
		end=vni_result[0]["end"]

		#予備経路検索
		sql = u"select * from flow_table where start="+str(start)+ " and end="+str(end) +" and vni!="+str(vni)
		vni_result = self.send_sql(sql,"local")
		req_ch_vni = vni_result[0]["vni"]

		#経路情報取得
		sql = u"select * from flow_table where start="+str(end)+ " and end="+str(start)
		route_result = self.send_sql(sql,"local")

		datapath = dpid_list[int(my_dpid)]
		ofp = datapath.ofproto
		ofp_parser = datapath.ofproto_parser

		num = 0
		while num < len(route_result):
			dinfo = ast.literal_eval(route_result[num]["actions"])

			#パケット組立
			pkt = packet.Packet()

			##MACFrame生成
			pkt.add_protocol(ethernet.ethernet(ethertype=2048,
							   dst="99:99:99:99:99:02",
							   src="99:99:99:99:99:01"))

			##IPFrame生成
			pkt.add_protocol(ipv4.ipv4(version=4,
								header_length=5,
								tos=0,
								total_length=0,
								identification=0,
								flags=0,
								offset=0,
								ttl=255,
								proto=0,
								csum=0,
								src='192.168.1.1',
								dst='192.168.1.2',
								option=None))

			##データ部生成
			#timestamp = float(time.perf_counter())
			timestamp = datetime.now().strftime("%Y/%m/%d %H-%M-%S.%f")
			print timestamp
			pkt.add_protocol(cfm.data_tlv(length=0, data_value="type:CR,timestamp:"+str(timestamp)+",dead_vxlan:"+str(vni)+",ch_vni:"+str(req_ch_vni)+","))
			pkt.serialize()
			data = pkt.data
			encap_vlan=datapath.ofproto_parser.OFPMatchField.make(ofp.OXM_OF_VLAN_VID,dinfo["vlan"])
			actions = [
						ofp_parser.OFPActionEncap(201397),
						ofp_parser.OFPActionSetField(vxlan_vni=dinfo["vni"]),
						ofp_parser.OFPActionEncap(131089),
						ofp_parser.OFPActionSetField(udp_src=10),
						ofp_parser.OFPActionSetField(udp_dst=4789),
						ofp_parser.OFPActionEncap(67584),
						ofp_parser.OFPActionSetField(ipv4_dst=dinfo["to_ip"]),
						ofp_parser.OFPActionSetField(ipv4_src=dinfo["from_ip"]),
						ofp_parser.OFPActionSetNwTtl(64),
						ofp_parser.OFPActionEncap(0),
						ofp_parser.OFPActionSetField(eth_dst=dinfo["to_mac"]),
						ofp_parser.OFPActionSetField(eth_src=dinfo["from_mac"]),
						ofp_parser.OFPActionPushVlan(ether.ETH_TYPE_8021Q),
						ofp_parser.OFPActionSetField(encap_vlan),
						ofp_parser.OFPActionOutput(dinfo["out_port"])
					]

			#パケット送信
			req = ofp_parser.OFPPacketOut( datapath=datapath,
												buffer_id=ofp.OFP_NO_BUFFER,
												in_port=ofp.OFPP_CONTROLLER,
												actions=actions,
												data=data)
			datapath.send_msg(req)
			num+=1
		return 0

	def RECEIVE_CC_PKT(self,vni,status,q):
		global dpid_list
		global oam

		dinfo = {}
		if status=="start":
			oam["cc"][vni] = {}
			oam["cc"][vni]["minimum"] = 0
			oam["cc"][vni]["status"] = "pending"
			oam["cc"][vni]["serial"] = 0
			oam["cc"][vni]["log_id"] = datetime.now().strftime("%Y%m%d%H%M%S")
			oam["cc"][vni]["log_date"] = datetime.now().strftime("%Y/%m/%d")
		else:
			oam["cc"][vni]["status"] = "stop"

		print oam["cc"][vni]["status"]
		#VNIから経路検索
		sql = u"select * from vnilist where vxlanid="+str(vni)
		vni_result = self.send_sql(sql,"center")

		port =  vni_result[0]["path"][2:-2].replace('L', '').split("], [")[-3].split(", ")
		try:
			datapath = dpid_list[int(port[0][:-3])]
			ofp = datapath.ofproto
			ofp_parser = datapath.ofproto_parser
			in_port = int(port[1])
		except:
			q.put("No Connected OFS")

		device_sql = u"select * from port where did="+str(int(port[0][:-3]))+" and interface="+str(in_port)
		device_result = self.send_sql(device_sql,"center")

		#match  = ofp_parser.OFPMatch(in_port=in_port,eth_dst=device_result[0]["macaddr"],eth_type=2048,ip_proto=17,udp_src=2,vxlan_vni=vni)
		match  = ofp_parser.OFPMatch(in_port=in_port,eth_type=2048,ip_proto=17,udp_src=4,vxlan_vni=vni)
		if status == "start":
			dinfo["mode"] = "decap"
		elif status == "stop":
			dinfo["mode"] = "delete_flow"
		dinfo["priority"] = 600
		dinfo["out_port"] = ofproto_v1_3.OFPP_CONTROLLER

		self.insert_flow(datapath,match,dinfo)

		q.put("complete")


	# LBパケット構築
	def Build_OAM_LB(self,vni,mtu,sport,dport):
		#グローバル変数
		global oam

		dinfo = {}
		dinfo["vni"] = vni

		#VNIから経路検索
		sql = u"select * from vnilist where vxlanid="+str(vni)
		vni_result = self.send_sql(sql,"center")

		#送出デバイスID検索
		dinfo["from"] =  vni_result[0]["path"][2:-2].replace('L', '').split("], [")[2].split(", ")[0]

		#送出ポート情報検索
		sql = u"select * from port where port_id='"+str(dinfo["from"]) + "'"
		from_result = self.send_sql(sql,"center")
		dinfo["out_port"] = from_result[0]["interface"]
		dinfo["from_mac"] = from_result[0]["macaddr"]
		dinfo["from_ip"] = from_result[0]["local_ip"]

		#ネクストホップ検索
		dinfo["to"] = vni_result[0]["path"][2:-2].replace('L', '').split("], [")[3].split(", ")[0]
		nextloc = int(str(dinfo["to"])[:-6])
		sql = u"select * from port where port_id='"+str(dinfo["to"]) + "'"
		to_result = self.send_sql(sql,"center")
		dinfo["to_mac"] = to_result[0]["macaddr"]
		dinfo["to_ip"] = to_result[0]["local_ip"]

		sql = u"select * from physical_link where port_id1="+str(dinfo["from"])+" and port_id2="+str(dinfo["to"])
		result = self.send_sql(sql,"center")
		if len(result)==0:
			sql = u"select * from physical_link where port_id1="+str(dinfo["to"])+" and port_id2="+str(dinfo["from"])
			result = self.send_sql(sql,"center")
			if len(result)!=0:
				dinfo["vlan"]=result[0]["vlan2"]
		else:
			dinfo["vlan"]=result[0]["vlan1"]


		#インターネット経路の場合
		if nextloc == 1:
			dinfo["to"] = vni_result[0]["path"][2:-2].replace('L', '').split("], [")[5].split(", ")[0]
			dinfo["from_ip"] = from_result[0]["global_ip"]
			sql = u"select * from port where port_id='"+str(dinfo["to"]) + "'"
			to_result = self.send_sql(sql,"center")
			dinfo["to_ip"] = to_result[0]["global_ip"]

		dinfo["from"] = dinfo["from"][:-3]

		#DPID取得
		datapath = dpid_list[int(dinfo["from"])]
		ofproto = datapath.ofproto
		ofp_parser = datapath.ofproto_parser

		dinfo["mode"] = "decap"
		dinfo["priority"] = 700
		dinfo["tmp_out_port"] = dinfo["out_port"]
		dinfo["out_port"] = ofproto_v1_3.OFPP_CONTROLLER
		oam["lb"][dinfo["vni"]]["match"]  = ofp_parser.OFPMatch(in_port=dinfo["tmp_out_port"],eth_type=2048,ip_proto=17,udp_src=sport)
		oam["lb"][dinfo["vni"]]["dpid"]=dinfo["from"]
		result = self.insert_flow(datapath,oam["lb"][dinfo["vni"]]["match"] ,dinfo)

		dinfo["out_port"] = dinfo["tmp_out_port"]

		#パケット組立
		pkt = packet.Packet()

		##MACFrame生成
		pkt.add_protocol(ethernet.ethernet(ethertype=2048,
						   dst="00:ac:b8:c2:f9:01",
						   src="00:ac:b8:c2:f9:00"))

		##IPFrame生成
		pkt.add_protocol(ipv4.ipv4(version=4,
							header_length=5,
							tos=0,
							total_length=0,
							identification=0,
							flags=0,
							offset=0,
							ttl=255,
							proto=0,
							csum=0,
							src='192.168.1.1',
							dst='192.168.1.2',
							option=None))

		##データ部生成
		#timestamp = float(time.perf_counter())
		timestamp = datetime.now().strftime("%Y/%m/%d %H-%M-%S.%f")

		pkttest = packet.Packet()
		pkttest.add_protocol(cfm.data_tlv(length=0, data_value="type:LB,timestamp:"+str(timestamp)+",serialnumber:1,vxlanid:"+str(dinfo["vni"])+","))
		pkttest.serialize()
		data_test = pkttest.data
		#PKTサイズ可変処理
		size = int(mtu) - len(data_test)
		num = 0
		tmp = ""
		while num<size:
			tmp = tmp + str("0")
			num += 1

		pkt.add_protocol(cfm.data_tlv(length=0, data_value="type:LB,timestamp:"+str(timestamp)+",serialnumber:1,vxlanid:"+str(dinfo["vni"])+","+str(tmp)))
		pkt.serialize()
		data = pkt.data


		encap_vlan=datapath.ofproto_parser.OFPMatchField.make(ofproto.OXM_OF_VLAN_VID,dinfo["vlan"])
		actions = [
					ofp_parser.OFPActionEncap(201397),
					ofp_parser.OFPActionSetField(vxlan_vni=dinfo["vni"]),
					ofp_parser.OFPActionEncap(131089),
					ofp_parser.OFPActionSetField(udp_src=sport),
					ofp_parser.OFPActionSetField(udp_dst=dport),
					ofp_parser.OFPActionEncap(67584),
					ofp_parser.OFPActionSetField(ipv4_dst=dinfo["to_ip"]),
					ofp_parser.OFPActionSetField(ipv4_src=dinfo["from_ip"]),
					ofp_parser.OFPActionSetNwTtl(64),
					ofp_parser.OFPActionEncap(0),
					ofp_parser.OFPActionSetField(eth_dst=dinfo["to_mac"]),
					ofp_parser.OFPActionSetField(eth_src=dinfo["from_mac"]),
					ofp_parser.OFPActionPushVlan(ether.ETH_TYPE_8021Q),
					ofp_parser.OFPActionSetField(encap_vlan),
					ofp_parser.OFPActionOutput(dinfo["out_port"])
				]

		#パケット送信
		req = ofp_parser.OFPPacketOut( datapath=datapath,
											buffer_id=ofproto.OFP_NO_BUFFER,
											in_port=ofproto.OFPP_CONTROLLER,
											actions=actions,
											data=data)
		datapath.send_msg(req)
		return dinfo

	# LBパケット構築
	def LBTurnBack(self,vni,hop,sport,dport):
		#グローバル変数
		global oam

		dinfo = {}
		receive_vni = vni

		#VNIから経路検索
		sql = u"select * from vnilist where vxlanid="+str(vni)
		vni_result = self.send_sql(sql,"center")

		#往路のパス情報から復路のパス情報を検索
		path = ast.literal_eval(vni_result[0]["path"])
		Reverse_path = []
		for i in reversed(xrange(len(path))):
			Reverse_path.append(path[i])
		sql = u"select * from vnilist where path='"+str(Reverse_path)+"'"
		result = self.send_sql(sql,"center")
		path = ast.literal_eval(result[0]["path"])

		dinfo["vni"] = result[0]["vxlanid"]
		dinfo["from"] = str(path[-hop][0])
		dinfo["to"] = str(path[-hop+1][0])

		#送出ポート情報検索
		sql = u"select * from port where port_id='"+str(dinfo["from"]) + "'"
		from_result = self.send_sql(sql,"center")
		dinfo["out_port"] = from_result[0]["interface"]
		dinfo["from_mac"] = from_result[0]["macaddr"]
		dinfo["from_ip"] = from_result[0]["local_ip"]

		#ネクストホップ検索
		nextloc = int(str(dinfo["to"])[:-6])
		sql = u"select * from port where port_id='"+str(dinfo["to"]) + "'"
		to_result = self.send_sql(sql,"center")
		dinfo["to_mac"] = to_result[0]["macaddr"]
		dinfo["to_ip"] = to_result[0]["local_ip"]

		sql = u"select * from physical_link where port_id1="+str(dinfo["from"])+" and port_id2="+str(dinfo["to"])
		result = self.send_sql(sql,"center")
		if len(result)==0:
			sql = u"select * from physical_link where port_id1="+str(dinfo["to"])+" and port_id2="+str(dinfo["from"])
			result = self.send_sql(sql,"center")
			if len(result)!=0:
				dinfo["vlan"]=result[0]["vlan2"]
		else:
			dinfo["vlan"]=result[0]["vlan1"]

		#インターネット経路の場合
		if nextloc == 1:
			dinfo["to"] = vni_result[0]["path"][2:-2].replace('L', '').split("], [")[2].split(", ")[0]
			dinfo["from_ip"] = from_result[0]["global_ip"]
			pprint(dinfo)
			sql = u"select * from port where port_id='"+str(dinfo["to"]) + "'"
			to_result = self.send_sql(sql,"center")
			pprint(to_result)
			dinfo["to_ip"] = to_result[0]["global_ip"]

		dinfo["from"] = dinfo["from"][:-3]
		dinfo["priority"] = 700
		dinfo["mode"] = "recap"
		dinfo["sport"] = sport
		dinfo["dport"] = dport

		#DPID取得
		datapath = dpid_list[int(dinfo["from"])]
		ofproto = datapath.ofproto
		ofp_parser = datapath.ofproto_parser

		match = ofp_parser.OFPMatch(in_port=dinfo["out_port"],eth_type=2048,ip_proto=17,udp_src=sport,vxlan_vni=receive_vni)
		oam["lb"][vni]["dpid"] = dinfo["from"]
		oam["lb"][vni]["match"] = match
		result = self.insert_flow(datapath,match,dinfo)
		print result
		return result

	# LBパケット受信停止
	def LBTurnOff(self,vni):
		#グローバル変数
		global oam

		dinfo = {}
		dinfo["mode"] = "delete_flow"
		dinfo["priority"] = 700

		#DPID取得
		datapath = dpid_list[int(oam["lb"][vni]["dpid"])]
		ofproto = datapath.ofproto
		ofp_parser = datapath.ofproto_parser

		match = oam["lb"][vni]["match"]
		result = self.insert_flow(datapath,match,dinfo)
		return result

	# CCパケット構築
	def Build_OAM_CC(self,vni,q):
		#グローバル変数
		global oam

		dinfo = {}
		dinfo["vni"] = vni

		#配列初期化
		oam["cc"][vni] = {}
		oam["cc"][vni]["serial"] = 0
		oam["cc"][vni]["status"] = "start"

		#VNIから経路検索
		sql = u"select * from vnilist where vxlanid="+str(vni)
		vni_result = self.send_sql(sql,"center")

		#送出デバイスID検索
		dinfo["from"] =  vni_result[0]["path"][2:-2].replace('L', '').split("], [")[2].split(", ")[0]

		#送出ポート情報検索
		sql = u"select * from port where port_id='"+str(dinfo["from"]) + "'"
		from_result = self.send_sql(sql,"center")
		dinfo["out_port"] = from_result[0]["interface"]
		dinfo["from_mac"] = from_result[0]["macaddr"]
		dinfo["from_ip"] = from_result[0]["local_ip"]

		#ネクストホップ検索
		dinfo["to"] = vni_result[0]["path"][2:-2].replace('L', '').split("], [")[3].split(", ")[0]
		nextloc = int(str(dinfo["to"])[:-6])
		sql = u"select * from port where port_id='"+str(dinfo["to"]) + "'"
		to_result = self.send_sql(sql,"center")
		dinfo["to_mac"] = to_result[0]["macaddr"]
		dinfo["to_ip"] = to_result[0]["local_ip"]

		sql = u"select * from physical_link where port_id1="+str(dinfo["from"])+" and port_id2="+str(dinfo["to"])
		result = self.send_sql(sql,"center")
		if len(result)==0:
			sql = u"select * from physical_link where port_id1="+str(dinfo["to"])+" and port_id2="+str(dinfo["from"])
			result = self.send_sql(sql,"center")
			if len(result)!=0:
				dinfo["vlan"]=result[0]["vlan2"]
		else:
			dinfo["vlan"]=result[0]["vlan1"]

		#インターネット経路の場合
		if nextloc == 1:
			dinfo["to"] = vni_result[0]["path"][2:-2].replace('L', '').split("], [")[5].split(", ")[0]
			sql = u"select * from port where port_id='"+str(dinfo["to"]) + "'"
			to_result = self.send_sql(sql,"center")
			dinfo["from_ip"] = from_result[0]["global_ip"]
			dinfo["to_ip"] = to_result[0]["global_ip"]
		dinfo["from"] = dinfo["from"][:-3]

		#CCパケット送信処理
		th_id=str(vni)+"_0"
		t = threading.Thread(target=self.send_cc_pkt,name=th_id,args=(dinfo,dinfo["vni"],0))
		t.start()
		q.put(dinfo)

	def send_cc_pkt(self,dinfo,vni,th_id):
		global dpid_list
		global oam

		time.sleep(1)

		if th_id==0:
			th_id=1
		else:
			th_id=0

		th_name=str(vni)+str(th_id)
		t = threading.Thread(target=self.send_cc_pkt,name=th_name,args=(dinfo,dinfo["vni"],th_id))
		#t = send_cc_pkt(dinfo,dinfo["vni"])
		if oam["cc"][dinfo["vni"]]["status"] == "start":
			t.start()
		else:
			pass

		#カウンタアップ
		oam["cc"][dinfo["vni"]]["serial"] = oam["cc"][dinfo["vni"]]["serial"] + 1

		#DPID取得
		datapath = dpid_list[int(dinfo["from"])]
		ofproto = datapath.ofproto
		ofp_parser = datapath.ofproto_parser

		#パケット組立
		pkt = packet.Packet()

		##MACFrame生成
		pkt.add_protocol(ethernet.ethernet(ethertype=2048,
						   dst="00:ac:b8:c2:f9:01",
						   src="00:ac:b8:c2:f9:00"))

		##IPFrame生成
		pkt.add_protocol(ipv4.ipv4(version=4,
							header_length=5,
							tos=0,
							total_length=0,
							identification=0,
							flags=0,
							offset=0,
							ttl=255,
							proto=0,
							csum=0,
							src='192.168.1.1',
							dst='192.168.1.2',
							option=None))

		##データ部生成
		#timestamp = float(time.perf_counter())
		num=0
		tmp = ""
		while num<1000:
			tmp = tmp + str("0")
			num += 1

		timestamp = datetime.now().strftime("%Y/%m/%d %H-%M-%S.%f")
		pkt.add_protocol(cfm.data_tlv(length=0, data_value="type:CC,timestamp:"+str(timestamp)+",serialnumber:"+str(oam["cc"][dinfo["vni"]]["serial"])+",vxlanid:"+str(dinfo["vni"])+","+str(num)))
		pkt.serialize()
		data = pkt.data

		encap_vlan=datapath.ofproto_parser.OFPMatchField.make(ofproto.OXM_OF_VLAN_VID,dinfo["vlan"])
		actions = [
					ofp_parser.OFPActionEncap(201397),
					ofp_parser.OFPActionSetField(vxlan_vni=dinfo["vni"]),
					ofp_parser.OFPActionEncap(131089),
					ofp_parser.OFPActionSetField(udp_src=4),
					ofp_parser.OFPActionSetField(udp_dst=4789),
					ofp_parser.OFPActionEncap(67584),
					ofp_parser.OFPActionSetField(ipv4_dst=dinfo["to_ip"]),
					ofp_parser.OFPActionSetField(ipv4_src=dinfo["from_ip"]),
					ofp_parser.OFPActionSetNwTtl(64),
					ofp_parser.OFPActionEncap(0),
					ofp_parser.OFPActionSetField(eth_dst=dinfo["to_mac"]),
					ofp_parser.OFPActionSetField(eth_src=dinfo["from_mac"]),
					ofp_parser.OFPActionPushVlan(ether.ETH_TYPE_8021Q),
					ofp_parser.OFPActionSetField(encap_vlan),
					ofp_parser.OFPActionOutput(dinfo["out_port"])
				]

		#パケット送信
		req = ofp_parser.OFPPacketOut( datapath=datapath,
											buffer_id=ofproto.OFP_NO_BUFFER,
											in_port=ofproto.OFPP_CONTROLLER,
											actions=actions,
											data=data)
		datapath.send_msg(req)

def ws():
	api.run(host='0.0.0.0', port=3000, threaded=True)
webserver=threading.Thread(target=ws)
webserver.start()

#Localルート設定
@api.route('/oam/cc/send/start/<int:vni>', methods=['GET'])
def OAM_CC_SendStart(vni):
	global oam
	q = Queue()
	me = Open_SDWAN()
	result = threading.Thread(target=me.Build_OAM_CC,name="start_cc",args=(vni,q))
	result.start()
	result.join()
	result = q.get()

	if isinstance(result, str):
		result = {"result":str(result)}
	else:
		result = {
			"result": str(result)
			}
	return make_response(jsonify(result))

#Localルート設定
@api.route('/oam/lb/send/<int:vni>/<int:mtu>/<int:sport>/<int:dport>', methods=['GET'])
def OAM_LB_Send(vni,mtu,sport,dport):
	global oam
	oam["lb"][vni] = {}
	oam["lb"][vni]["status"] = "start"
	oam["lb"][vni]["delay"] = 0.0

	me = Open_SDWAN()
	result = me.Build_OAM_LB(vni,mtu,sport,dport)

	counter = 0
	while(True):
		if oam["lb"][vni]["status"] == "turnback":
			result = {"result":str(oam["lb"][vni]["delay"])}
			break
		time.sleep(1)
		counter+=1

		if counter == 10:
			result = "timeover"
			break

	result = {"result":str(result)}
	return make_response(jsonify(result))

@api.route('/oam/lb/receive/<int:vni>/<int:hop>/<int:sport>/<int:dport>', methods=['GET'])
def OAM_LB_Receive(vni,hop,sport,dport):
	global oam
	oam["lb"][vni] = {}

	me = Open_SDWAN()
	result = me.LBTurnBack(vni,hop,sport,dport)
	if isinstance(result, str):
		result = {"result":str(result)}
	else:
		result = {
			"result": str(result)
			}
	return make_response(jsonify(result))

@api.route('/oam/lb/stop/<int:vni>', methods=['GET'])
def OAM_LB_Stop(vni):
	global oam

	me = Open_SDWAN()
	result = me.LBTurnOff(vni)
	result = {"result":str(result)}
	return make_response(jsonify(result))


@api.route('/oam/cc/receive/start/<int:vni>', methods=['GET'])
def OAM_CC_ReceiveStart(vni):
	q = Queue()
	me = Open_SDWAN()

	result = threading.Thread(target=me.RECEIVE_CC_PKT,name="receive_start",args=(vni,"start",q))
	result.start()
	result.join()
	result = q.get()

	if isinstance(result, str):
		result = {"result":str(result)}
	else:
		result = {
			"result": str(result)
			}
	return make_response(jsonify(result))

#Localルート設定
@api.route('/oam/cc/send/stop/<int:vni>', methods=['GET'])
def OAM_CC_SendStop(vni):
	global oam

	#処理停止指示
	while(True):
		#停止処理
		oam["cc"][vni]["status"] = "stop"
		time.sleep(1)
		#現シリアル確認
		serial = oam["cc"][vni]["serial"]
		time.sleep(1)
		#シリアル比較
		diff = oam["cc"][vni]["serial"] - serial
		#シリアルがカウントアップしてなければ終了
		if diff == 0:
			result = {"result": "complete"}
			break
		#シリアルがカウントアップしていれば
		#再度停止処理実施
		else:
			pass
	return make_response(jsonify(result))

@api.route('/oam/cc/receive/stop/<int:vni>', methods=['GET'])
def OAM_CC_ReceiveStop(vni):
	global oam
	me = Open_SDWAN()
	q = Queue()
	result = threading.Thread(target=me.RECEIVE_CC_PKT,name="receive_stop",args=(vni,"stop",q))
	result.start()
	result.join()
	result = q.get()
	if isinstance(result, str):
		result = {"result":str(result)}
	else:
		result = {
			"result": str(result)
			}
	return make_response(jsonify(result))

#Localルート設定
@api.route('/route_add/<string:start>/<string:end>/<string:vni>/<string:path_type>/<string:path>', methods=['GET'])
def VXLAN_Route_Add(start,end,vni,path_type,path):
	me = Open_SDWAN()
	sql = u"insert into logical_link (start,end,vni,path_type,path) values('"+str(start)+"', '"+str(end)+"', '"+str(vni)+"', '"+str(path_type)+"', '"+str(path)+"')"
	result = me.send_sql(sql,"local")

	result = {"result": "complete"}
	return make_response(jsonify(result))

#Localルート設定
@api.route('/sql/<string:sql>', methods=['GET'])
def Get_SQL(sql):
	me = Open_SDWAN()
	result = me.send_sql(sql,"local")

	result = {"result": "complete"}
	return make_response(jsonify(result))


#Localルート設定
@api.route('/route_delete/<string:start>/<string:end>', methods=['GET'])
def VXLAN_Route_Delete(start,end):
	me = Open_SDWAN()
	sql = u"DELETE FROM logical_link WHERE (start="+str(start)+" and end=" + str(end) +") or (start="+str(end)+" and end=" + str(start) +")"
	result = me.send_sql(sql,"local")
	result = {"result": "complete"}
	return make_response(jsonify(result))

@api.route('/chroute/<int:vni>', methods=['GET'])
def Request_ChangeRoute_API(vni):
	global oam

	me = Open_SDWAN()
	result = me.Request_ChangeRoute(vni)
	result = {"result":str("0000")}
	return make_response(jsonify(result))


class Proceed_PKT_IN(threading.Thread):

	def __init__(self,ev,receive_time):
		self.ev = ev
		self.receive_time = receive_time
		threading.Thread.__init__(self)

	def run(self):
		global oam
		global producer
		global portdata
		global dpid_list
		global my_dpid

		me = Open_SDWAN()

		#パケット受信時間
		receive_time = self.receive_time

		with smp:
			#パケット解体
			msg = self.ev.msg
			return_port = msg.match['in_port']
			datapath = msg.datapath
			ofproto = datapath.ofproto
			parser = datapath.ofproto_parser

			check_pkt = packet.Packet(array.array('B', msg.data))
			p_arp = self._find_protocol(check_pkt, "arp")
			p_icmp = self._find_protocol(check_pkt, "icmp")
			p_ipv4 = self._find_protocol(check_pkt, "ipv4")

			if p_arp:
				src_ip = str(netaddr.IPAddress(p_arp.src_ip))
				dst_ip = str(netaddr.IPAddress(p_arp.dst_ip))
				eth = check_pkt.get_protocols(ethernet.ethernet)[0]
				dstmac = eth.src

				if p_arp.opcode == arp.ARP_REQUEST:
					if len(portdata)==0:
						sql = u"select * from port where did="+str(datapath.id)+" order by interface ASC"
						portdata = me.send_sql(sql,"center")

				try:
					if portdata[return_port-1]["global_ip"] == dst_ip:
						hostmac=portdata[return_port-1]["macaddr"]
						print "--- PacketIn: ARP_Request: " + str(src_ip) + "=>" + str(dst_ip)
						data = self._arp_reply(dst_ip,src_ip,hostmac,dstmac)
						self._send_msg(datapath, data,return_port)
				except:
					pass
			elif p_icmp:
				src_ip = str(netaddr.IPAddress(p_ipv4.src))
				dst_ip = str(netaddr.IPAddress(p_ipv4.dst))
				eth = check_pkt.get_protocols(ethernet.ethernet)[0]
				dst_mac = eth.src
				icmp_error = False
				if p_icmp.type == icmp.ICMP_ECHO_REQUEST:
					try:
						echo = p_icmp.data
						echo.data = bytearray(echo.data)
					except Exception as e:
						icmp_error = True

					if icmp_error==False:
						if len(portdata)==0:
							sql = u"select * from port where did="+str(datapath.id)+" order by interface ASC"
							portdata = me.send_sql(sql,"center")
						try:
							hostmac=portdata[return_port-1]["macaddr"]
							ipaddr=portdata[return_port-1]["global_ip"]
							if dst_ip == ipaddr:
								print "--- PacketIn: Echo_Request:" + src_ip + "=>" + dst_ip
								data = self._echo_reply(echo,dst_ip,src_ip,hostmac,dst_mac)
								self._send_msg(datapath, data,return_port)
							else:
								pass
						except:
							pass

			elif p_ipv4:
				pkt = packet.Packet(msg.data)
				eth = pkt.get_protocols(ethernet.ethernet)[0]
				dst = eth.dst
				src = eth.src

				try:
					data = pkt.data.split("data_value='")[1].split("'")[0].split(",")
					oamtype = data[0].split(":")[1]
					timestamp = data[1].split(":")[1]
					serial = data[2].split(":")[1]
					vxlanid = int(data[3].split(":")[1])
				except:
					print "split error"
					return True

				if oamtype == "LB":
					oam["lb"][vxlanid]["status"] = "turnback"
					receive_time	= dt.datetime.strptime(receive_time,'%Y/%m/%d %H-%M-%S.%f')
					timestamp		= dt.datetime.strptime(timestamp,'%Y/%m/%d %H-%M-%S.%f')
					jitter = receive_time - timestamp
					oam["lb"][vxlanid]["delay"] = float(jitter.total_seconds())

				if oamtype == "CR":
					datapath = dpid_list[int(my_dpid)]
					ofp = datapath.ofproto
					ofp_parser = datapath.ofproto_parser

					sql = u"select * from flow_table where vni="+str(vxlanid)
					result = me.send_sql(sql,"local")
					if result[0]["category"] != "Primary":
						match = ast.literal_eval(result[0]["flow_match"].replace('OFPMatch(oxm_fields=','').replace(')',''))
						match = ofp_parser.OFPMatch(**match)
						dinfo = ast.literal_eval(result[0]["actions"])
						dinfo["priority"] = 400
						change_pri_result = me.insert_flow(datapath,match,dinfo)

						try:
							sec_sql = u"update flow_table set actions=\"" + str(dinfo) +"\",category=\"Primary\" where vni=" + str(vxlanid) + " and dpid="+str(my_dpid)
							sec_result = me.send_sql(sec_sql,"local")
							receive_url = str(Master_Controller_URL)+"/sql/" + str(sec_sql)
							receive_result = requests.get(receive_url)
						except:
							pass

						try:
							sec_sql = u"update flow_table set category=\"Primary\" where vni=" + str(vxlanid) + " and dpid="+str(my_dpid)
							sec_result = me.send_sql(sec_sql,"local")
							receive_url = str(Master_Controller_URL)+"/sql/" + str(sec_sql)
							receive_result = requests.get(receive_url)
						except:
							pass

						try:
							sql = u"select * from flow_table where start="+str(result[0]["start"])+ " and end="+str(result[0]["end"]) +" and vni!="+str(vxlanid)
							vni_result = me.send_sql(sql,"local")

							#PrimaryRouteの優先度をSecondaryRouteの値に修正
							match = ast.literal_eval(vni_result[0]["flow_match"].replace('OFPMatch(oxm_fields=','').replace(')',''))
							match = ofp_parser.OFPMatch(**match)
							dinfo = ast.literal_eval(vni_result[0]["actions"])
							dinfo["priority"] = 300
							change_pri_ = me.insert_flow(datapath,match,dinfo)
						except:
							pass

						try:
							pri_sql = u"update flow_table set actions=\"" + str(dinfo) +"\",category=\"Secondary\" where vni=" + str(vni_result[0]["vni"]) + " and dpid="+str(my_dpid)
							pri_result = me.send_sql(pri_sql,"local")
							receive_url = str(Master_Controller_URL)+"/sql/" + str(pri_sql)
							receive_result = requests.get(receive_url)
						except:
							pass

				if oamtype == "CC":
					if oam["cc"].has_key(vxlanid)==True:
						oam["cc"][vxlanid]["serial"] = serial

						if oam["cc"][vxlanid]["status"] == "pending":
							oam["cc"][vxlanid]["status"] = "operation"
							oam["cc"][vxlanid]["unreceived"] = 0
							me = Open_SDWAN()

							t = CheckRoute(vxlanid,serial)
							t.start()

						#時間処理
						receive_time	= dt.datetime.strptime(receive_time,'%Y/%m/%d %H-%M-%S.%f')
						timestamp		= dt.datetime.strptime(timestamp,'%Y/%m/%d %H-%M-%S.%f')
						jitter = receive_time - timestamp
						jitter = float(jitter.total_seconds())

						#時間変換(JST=>UTC)
						utc = pytz.timezone('UTC')
						jst = pytz.timezone('Asia/Tokyo')
						timestamp = jst.localize(timestamp)
						timestamp = str(timestamp.astimezone(utc))[:-6]

						receive_time = jst.localize(receive_time)
						receive_time = str(receive_time.astimezone(utc))[:-6]


						if float(oam["cc"][vxlanid]["minimum"]) > jitter or float(oam["cc"][vxlanid]["minimum"])==0.0:
							oam["cc"][vxlanid]["minimum"] = jitter

						#print "dpid: " + str(datapath.id) + " ,oamtype:" + str(oamtype) + " ,timestamp:" + str(timestamp) + " ,jitter:" + str(jitter) + " ,minimum:" + str(oam["cc"][vxlanid]["minimum"]) + " ,serial:" + str(serial) + " ,vni:" + str(vxlanid)

						logid_date	= dt.datetime.strptime(oam["cc"][vxlanid]["log_date"],'%Y/%m/%d')
						logid_now	= dt.datetime.strptime(datetime.now().strftime("%Y/%m/%d"),'%Y/%m/%d')
						logid_diff	= logid_now - logid_date
						logid_diff	= int(logid_diff.total_seconds())
						if logid_diff != 0:
							oam["cc"][vxlanid]["log_id"] = datetime.now().strftime("%Y%m%d%H%M%S")
							oam["cc"][vxlanid]["log_date"] = datetime.now().strftime("%Y/%m/%d")

						url="niipj-"+str(vxlanid)+'-'+str(oam["cc"][vxlanid]["log_id"])

						kafkaid=vxlanid%10
						send_result = producer.send('oam-cc-data'+str(kafkaid), b"%s,%s,%s,%s,%s,%s,%s"%(url,receive_time,timestamp,oam["cc"][vxlanid]["minimum"],jitter,serial,vxlanid))
			with lock:
				pass
		return True

	def _find_protocol(self, pkt, name):
		for p in pkt.protocols:
			if hasattr(p, 'protocol_name'):
				if p.protocol_name == name:
					return p

	def _arp_reply(self,hostip,dstip,hostmac,dstmac):
		p = self._build_arp(arp.ARP_REPLY, hostip,dstip,hostmac,dstmac)
		return p.data

	def _build_ether(self, ethertype, hostmac,dstmac):
		e = ethernet.ethernet(dstmac, hostmac, ethertype)
		return e

	def _build_arp(self, opcode, hostip,dstip,hostmac,dstmac):
		e = self._build_ether(ether.ETH_TYPE_ARP, hostmac,dstmac)
		a = arp.arp(hwtype=1, proto=ether.ETH_TYPE_IP, hlen=6, plen=4,opcode=opcode, src_mac=hostmac, src_ip=hostip,dst_mac=dstmac,dst_ip=dstip)
		p = packet.Packet()
		p.add_protocol(e)
		p.add_protocol(a)
		p.serialize()

		return p


	def _echo_reply(self, echo,hostip,dstip,hostmac,dstmac):
		p = self._build_echo(icmp.ICMP_ECHO_REPLY, echo,hostip,dstip,hostmac,dstmac)
		return p.data

	def _build_echo(self, _type, echo,hostip,dstip,hostmac,dstmac):
		e = self._build_ether(ether.ETH_TYPE_IP,hostmac,dstmac)
		ip = ipv4.ipv4(version=4, header_length=5, tos=0, total_length=84,identification=0, flags=0, offset=0, ttl=64,proto=inet.IPPROTO_ICMP, csum=0,src=hostip, dst=dstip)
		ping = icmp.icmp(_type, code=0, csum=0, data=echo)

		p = packet.Packet()
		p.add_protocol(e)
		p.add_protocol(ip)
		p.add_protocol(ping)
		p.serialize()
		return p

	def _send_msg(self, dp, data,port):
		encap_vlan =dp.ofproto_parser.OFPMatchField.make(dp.ofproto.OXM_OF_VLAN_VID,ArpReply_Vlan)
		buffer_id = 0xffffffff
		in_port = dp.ofproto.OFPP_LOCAL
		actions = [dp.ofproto_parser.OFPActionPushVlan(ether.ETH_TYPE_8021Q),dp.ofproto_parser.OFPActionSetField(encap_vlan),dp.ofproto_parser.OFPActionOutput(port)]
		msg = dp.ofproto_parser.OFPPacketOut(dp, buffer_id, in_port, actions, data)
		dp.send_msg(msg)

class CheckRoute(threading.Thread):
	def __init__(self,vni,serial):
		self.vni = vni
		self.serial = serial
		threading.Thread.__init__(self)

	def run(self):
		global oam

		me = Open_SDWAN()
		time.sleep(1)

		t = CheckRoute(self.vni,oam["cc"][self.vni]["serial"])

		#CC受信状態であれば実行
		if oam["cc"][self.vni]["status"] == "operation" or oam["cc"][self.vni]["status"]=="trouble":
			t.start()

			#シリアルが前回到着値と同じなら
			#未受信カウンタをアップ
			if (int(self.serial)) == int(oam["cc"][self.vni]["serial"]):
				print str(datetime.now().strftime("%Y/%m/%d %H-%M-%S.%f"))+" : Serial is insufficient"
				today_date = datetime.now().strftime("%Y%m%d")
				fout = open("./log/"+str(today_date)+".txt", "a")
				fout.writelines("Insufficient"+","+str(datetime.now().strftime("%Y/%m/%d %H-%M-%S.%f"))+","+str(self.vni)+","+str(oam["cc"][self.vni]["serial"])+"\n")
				fout.close()
				oam["cc"][self.vni]["unreceived"] += 1

			#シリアルが前回到着値以上なら
			#未受信カウンタをリセット
			elif (int(self.serial)) < int(oam["cc"][self.vni]["serial"]):
				if oam["cc"][self.vni]["status"] == "trouble":
					print str(datetime.now().strftime("%Y/%m/%d %H-%M-%S.%f"))+" : Serial is Operation"
				if oam["cc"][self.vni]["unreceived"] > 0:
					today_date = datetime.now().strftime("%Y%m%d")
					fout = open("./log/"+str(today_date)+".txt", "a")
					fout.writelines("Operation"+","+str(datetime.now().strftime("%Y/%m/%d %H-%M-%S.%f"))+","+str(self.vni)+","+str(oam["cc"][self.vni]["serial"])+"\n")
					fout.close()
				oam["cc"][self.vni]["unreceived"] = 0
				oam["cc"][self.vni]["status"] = "operation"

			#シリアルが前回到着値以下なら
			#アラート発報かつ未受信カウンタをリセット
			elif (int(self.serial)) > int(oam["cc"][self.vni]["serial"]):
				print str(datetime.now().strftime("%Y/%m/%d %H-%M-%S.%f"))+" : Serial is insufficient"
				oam["cc"][self.vni]["unreceived"] += 1
				#oam["cc"][self.vni]["unreceived"] = 0

			#シリアル未受信カウンタが
			#3になった→経路切替処理
			if oam["cc"][self.vni]["unreceived"] > 3 and oam["cc"][self.vni]["status"] == "operation":
				print str(self.vni) + "is Trouble"
				oam["cc"][self.vni]["status"] = "trouble"
				result = me.ChangeRoute(self.vni)
		return 0

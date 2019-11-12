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

#パケット生成用
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp
from ryu.lib.packet import ipv4
from ryu.lib.packet import cfm
from ryu.lib.packet import vlan
from ryu.lib.packet import icmp
from ryu.ofproto import inet
from ryu.ofproto import ether

from pprint import pprint


from Queue import Queue

#Mysql接続用
import MySQLdb
import MySQLdb.cursors

import re

#API用
from flask import Flask, jsonify, abort, make_response
import peewee
import json

#マルチスレッド用
import array
import netaddr
import time
import datetime
import threading
import math

import ast

#curl叩くためのライブラリ(PyCurl)
import unirest
import requests

#グローバル変数
api = Flask(__name__)
dpid_list={}

#経路探索モジュール
import networkx as nx
from itertools import islice


class Open_SDWAN(RyuApp):
	OFP_VERSIONS = [OFP_VERSION]

	def __init__(self, *args, **kwargs):
		super(Open_SDWAN, self).__init__(*args, **kwargs)

	@set_ev_cls(EventOFPSwitchFeatures, CONFIG_DISPATCHER)
	def switch_features_handler(self, ev):
		datapath = ev.msg.datapath
		ofp = datapath.ofproto
		ofp_parser = datapath.ofproto_parser
		#DPIDをDBに登録
		dpid_list[int(datapath.id)] = datapath

		#接続ログ書き出し
		self.logger.info('installing flow@'+str(datapath.id))

	#SQL実行
	def send_sql(self,sql):
		sqlbase = MySQLdb.connect(host="localhost",db="Open-SD-WAN",user="root",passwd="Openlab0508",charset="utf8",cursorclass=MySQLdb.cursors.DictCursor)
		sqlcon = sqlbase.cursor()
		sqlcon.execute(sql)
		sqlbase.commit()
		result = sqlcon.fetchall()
		sqlcon.close()
		sqlbase.close()
		return result

	#フロー挿入
	def insert_flow(self,datapath,match,dinfo):
		ofp = datapath.ofproto
		ofp_parser = datapath.ofproto_parser
		cookie = cookie_mask = 0
		table_id = 0
		idle_timeout = hard_timeout = 0
		buffer_id = ofp.OFP_NO_BUFFER
		priority = dinfo["priority"]

		#VXLAN Encap Edge
		if dinfo["mode"] == "encap":
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

		#VXLAN Decap Edge
		elif dinfo["mode"] == "decap":
			actions = [
						ofp_parser.OFPActionPopVlan(ether.ETH_TYPE_8021Q),
						ofp_parser.OFPActionDecap(cur_pkt_type=0, new_pkt_type=67584),
						ofp_parser.OFPActionDecap(cur_pkt_type=67584, new_pkt_type=131089),
						ofp_parser.OFPActionDecap(cur_pkt_type=131089, new_pkt_type=201397),
						ofp_parser.OFPActionDecap(cur_pkt_type=201397, new_pkt_type=0),
						ofp_parser.OFPActionOutput(dinfo["out_port"])
					]

		#フロー投入処理
		if dinfo["mode"] == "flow_delete":
			inst = []
			req = ofp_parser.OFPFlowMod(datapath, cookie, cookie_mask,
						table_id, ofp.OFPFC_DELETE,
						idle_timeout, hard_timeout,
						priority, buffer_id,
						ofp.OFPP_ANY, ofp.OFPG_ANY,
						ofp.OFPFF_SEND_FLOW_REM,
						match, inst)
		else:
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

	#フロー生成
	def generate_flow(self,link,vnipath,custom_match):
		global dpid_list

		i = 0
		for vni in link:
			num = 1
			while num < len(vni)-1:
				dinfo = {}

				#DeviceID取得
				dinfo["dpid"] = int(str(vni[num][0])[:-3])
				#VNI取得
				pprint(vnipath)
				dinfo["vni"] = vnipath[i][0]
				#in_port 情報取得
				dinfo["in_port"] = vni[num][1]
				#out_port 取得
				dinfo["out_port"] = vni[num+1][1]

				#VXLAN Encap Edge
				if num == 1:
					dinfo["mode"] ="encap"
				#VXLAN Decap Edge
				elif len(vni) == num+3:
					dinfo["mode"] = "decap"
				#VXLAN Throw Edge
				else:
					dinfo["mode"] = "throw"

				#使用する経路判定並びにMACアドレス/IPアドレス抽出
				if dinfo["mode"] == "encap" or dinfo["mode"] == "throw":
					#送信元ポート情報採取
					sql = u"select * from port where port_id='"+str(vni[num+1][0])+"'"
					result_from = self.send_sql(sql)

					#送信先ポート情報採取
					sql = u"select * from port where port_id='"+str(vni[num+2][0])+"'"
					result_to = self.send_sql(sql)

					sql = u"select * from physical_link where port_id1="+str(vni[num+1][0])+" and port_id2="+str(vni[num+2][0])
					result_vlan = self.send_sql(sql)
					if len(result_vlan)==0:
						sql = u"select * from physical_link where port_id1="+str(vni[num+2][0])+" and port_id2="+str(vni[num+1][0])
						result_vlan = self.send_sql(sql)
						if len(result_vlan)!=0:
							dinfo["vlan"] = result_vlan[0]["vlan2"]
					else:
						dinfo["vlan"] = result_vlan[0]["vlan1"]


					#ネクストホップの拠点番号確認
					nexthop = str(vni[num+2][0])[:-6]

					#ネクストホップがインターネット経路
					if int(nexthop) == 1:
						print "internet"
						#送信元MACアドレス
						dinfo["from_mac"] = result_from[0]["macaddr"]
						#送信元グローバルIPアドレス
						dinfo["from_ip"] = result_from[0]["global_ip"]

						#送信先MACアドレス(拠点内上位ルータ)
						dinfo["to_mac"] = result_to[0]["macaddr"]
						#送信先グローバルIPアドレス
						sql = u"select * from port where port_id='"+str(vni[num+4][0])+"'"
						result_to = self.send_sql(sql)
						dinfo["to_ip"] = result_to[0]["global_ip"]

					#ネクストホップがSINET/GEANT経路
					else:
						print "L2 Line"
						#送信元MACアドレス
						dinfo["from_mac"] = result_from[0]["macaddr"]
						#送信元IPアドレス
						dinfo["from_ip"] = result_from[0]["local_ip"]

						#送信先MACアドレス(拠点内上位ルータ)
						dinfo["to_mac"] = result_to[0]["macaddr"]
						#送信先IPアドレス
						dinfo["to_ip"] = result_to[0]["local_ip"]

				#上位ルータではない場合
				if dinfo["dpid"] >= 2000:
					datapath = dpid_list[dinfo["dpid"]]
					ofp = datapath.ofproto
					ofp_parser = datapath.ofproto_parser
					if dinfo["mode"] == "encap":
						if custom_match == 0:
							match = ofp_parser.OFPMatch(in_port=dinfo["in_port"])
						else:
							match = ofp_parser.OFPMatch(in_port=dinfo["in_port"],eth_type=2048,vlan_vid=int(custom_match))
					elif dinfo["mode"] == "decap":
						match = ofp_parser.OFPMatch(in_port=dinfo["in_port"],eth_type=2048,ip_proto=17,udp_src=1,vxlan_vni=dinfo["vni"])
					else:
						match = ofp_parser.OFPMatch(in_port=dinfo["in_port"],eth_type=2048,ip_proto=17,vxlan_vni=dinfo["vni"])

					if i%2==0:
						dinfo["priority"] = 400
						category = "Primary"
					else:
						dinfo["priority"] = 300
						category = "Secondary"
					sql = u"insert into flow_table (vni,dpid,start,end,category,flow_match,actions) values('" + str(dinfo["vni"]) + "','" + str(datapath.id)+ "','" + str(vni[0][0])[:-3] + "','" + str(vni[-1][0])[:-3]+ "','" + str(category) +"',\"" + str(match) + "\",\"" + str(dinfo) + "\")"
					result = self.send_sql(sql)

					device_sql = "select * from device where did="+str(datapath.id)
					device_result = self.send_sql(device_sql)

					receive_url = "http://"+str(device_result[0]["ipaddr"])+":3000/sql/" + str(sql)
					receive_result = requests.get(receive_url)

					self.insert_flow(datapath,match,dinfo)

				num += 2
			i += 1
		return 0

	#最短経路検索
	def route_search(self,start,end,custom_match):
		link = []
		vnipath = ""

		#生きている回線のみ抽出
		sql = u"select * from physical_link where live=0"
		result = self.send_sql(sql)

		#使用可能な回線があるか確認
		#なければ、All route unusable, or Not connect of database を返却
		if len(result)!=0:
			#有向グラフ 定義
			graph = nx.DiGraph()

			#有向グラフ ノード作成
			for datas in result:
				graph.add_node(str(datas["port_id1"])[:-3])
				graph.add_node(str(datas["port_id2"])[:-3])

			#有向グラフ エッジ作成
			for datas in result:
				graph.add_edge(str(datas["port_id1"])[:-3],str(datas["port_id2"])[:-3],weight=datas["weight"])
				graph.add_edge(str(datas["port_id2"])[:-3],str(datas["port_id1"])[:-3],weight=datas["weight"])

			#重み付け最短経路検索(上位2経路を取得)
			#パスが存在しない場合は、No route exists を返却
			#try:
			#正順経路検索
			path=list(islice(nx.shortest_simple_paths(graph, str(start), str(end), weight='weight'), 2))
			if len(path)!=0:
				for detailpath in path:
					link.append(self.route_obtain(detailpath))

			#逆順経路検索
			revpath=list(islice(nx.shortest_simple_paths(graph, str(end), str(start), weight='weight'), 2))
			if len(revpath)!=0:
				for detailpath in revpath:
					link.append(self.route_obtain(detailpath))

			#VNI取得/発行
			vnipath = self.payout_vni(link)

			#フロー生成
			self.generate_flow(link,vnipath,custom_match)
			#except:
				#link = "No route exists"
		else:
			link = "All route unusable, or Not connect of database"
		return link,vnipath


	#経路情報詳細検索
	def route_obtain(self,path):
		#経路情報取得
		i = 0
		link = []
		while(path):
			if len(path)!=i+1:
				sql = u"select * from physical_link where port_id1 LIKE '"+str(path[i])+"%' and port_id2 LIKE '"+str(path[i+1])+"%'"
				result = self.send_sql(sql)
				if len(result) ==0:
					sql = u"select * from physical_link where port_id2 LIKE '"+str(path[i])+"%' and port_id1 LIKE '"+str(path[i+1])+"%'"
					result = self.send_sql(sql)
					sql = u"select * from port where port_id ='"+str(result[0]["port_id2"])+"'"
					port2 = self.send_sql(sql)
					sql = u"select * from port where port_id ='"+str(result[0]["port_id1"])+"'"
					port1 = self.send_sql(sql)

					pprint(result)

					link.append([result[0]["port_id2"],port2[0]["interface"]])
					link.append([result[0]["port_id1"],port1[0]["interface"]])

				else:
					sql = u"select * from port where port_id ='"+str(result[0]["port_id1"])+"'"
					port1 = self.send_sql(sql)
					sql = u"select * from port where port_id ='"+str(result[0]["port_id2"])+"'"
					port2 = self.send_sql(sql)
					pprint(result)
					link.append([result[0]["port_id1"],port1[0]["interface"]])
					link.append([result[0]["port_id2"],port2[0]["interface"]])

				i+=1
			else:
				break
		return link

	#VXLAN ID 検索/払い出し処理
	def payout_vni(self,link):
		i = 0
		vnipath = []
		for path in link:
			#VNILISTに経路が登録されているか確認
			sql = u"select * from vnilist where path='"+str(link[i])+"'"
			result = self.send_sql(sql)

			#当該経路のVNIが存在しない場合
			if len(result)==0:
				#空き番検索(空き番がない場合は、次の番号を払い出し)
				sql = u"select vxlanid+1 from vnilist where (vxlanid + 1) NOT IN ( select vxlanid from vnilist)"
				result = self.send_sql(sql)

				#空き番回答がない場合は、VNILISTが空のため、1を挿入
				if len(result)==0:
					vniid = int("1")
				else:
					vniid = result[0]["vxlanid+1"]

				#経路をVNILISTに登録
				sql = u"insert into vnilist (vxlanid,path) values('"+str(vniid)+"', '"+str(link[i])+"')"
				result = self.send_sql(sql)

				#VNILISTをアップデート
				vnipath.append(vniid)
			else:
				#VNILISTをアップデート
				vnipath.append([result[0]["vxlanid"]])
			i+=1
		return vnipath

	def CC_Control(self,vni,status):
		error = False
		error_log = ""

		#VNIから経路検索
		sql = u"select * from vnilist where vxlanid="+str(vni)
		vni_result = self.send_sql(sql)

		try:
			#送信先デバイスID取得
			send_device =  vni_result[0]["path"][2:-2].replace('L', '').split("], [")[2].split(", ")[0][:-3]

			#受信先デバイスID取得
			receive_device =  vni_result[0]["path"][2:-2].replace('L', '').split("], [")[-3].split(", ")[0][:-3]
		except:
			return "DeviceID Parse Error"

		try:
			#受信先デバイス マネジメントIP取得
			sql = u"select * from device where did="+str(receive_device)
			result = self.send_sql(sql)

			counter = 0
			while(True):
				#受信開始/停止リクエスト送信
				receive_url = "http://" + str(result[0]["ipaddr"]) + ":3000/oam/cc/receive/"+str(status)+"/" + str(vni)
				receive_result = requests.get(receive_url)
				#結果成形
				receive_result = re.sub(r'\{\s+\"result\"\: \"', "", receive_result.text)
				receive_result = re.sub(r'\"\s+\}', "", receive_result)
				receive_result = receive_result.replace('\n', '')

				#問題なく結果取得できた場合
				if receive_result == "complete":
					break

				#5回連続失敗した場合
				elif counter == 5:
					error = True
					error_log = "CC End Node("+str(receive_device)+") not response"
					break

				#再試行処理
				else:
					counter += 1
					time.sleep(1)
		except:
			return "Incorrect of IP Address (DPID: " + str(receive_device) + ", IPAddress: " + str(result[0]["ipaddr"]) + ")"

		try:
			if error == False:
				counter = 0
				while(True):
					#送信先デバイス マネジメントIP取得
					sql = u"select * from device where did="+str(send_device)
					result = self.send_sql(sql)

					#送信開始/停止リクエスト送信
					send_url = "http://" + str(result[0]["ipaddr"]) + ":3000/oam/cc/send/"+str(status)+"/" + str(vni)
					send_result = requests.get(send_url)

					#結果成形
					if status == "start":
						send_result = send_result.text.replace('\n', '')
						send_result = re.sub(r'.*\'from\'\: u\'', "", send_result)
						send_result = re.sub(r'\'.+\}', "", send_result)
					else:
						send_result = re.sub(r'\{\s+\"result\"\: \"', "", send_result.text)
						send_result = re.sub(r'\"\s+\}', "", send_result)
						send_result = send_result.replace('\n', '')

					#問題なく結果取得できた場合
					if send_result == send_device:
						break
					elif send_result == "complete":
						break

					#5回連続失敗した場合
					elif counter == 5:
						error = True
						error_log = "CC Start Node("+str(receive_device)+") not response"
						break

					#再試行処理
					else:
						counter += 1
						time.sleep(1)

		except:
			return "Incorrect of IP Address (DPID: " + str(send_device) + ", IPAddress: " + str(result[0]["ipaddr"]) + ")"

		if error == True:
			return error_log
		else:
			return "complete"

	def LB_Control(self,vni,hop,mtu,sport,dport):
		error = False
		error_log = ""
		hop = int(hop)*2+2
		#VNIから経路検索
		sql = u"select * from vnilist where vxlanid="+str(vni)
		vni_result = self.send_sql(sql)
		vni_result = ast.literal_eval(vni_result[0]["path"])
		try:
			#送信先デバイスID取得
			send_device =  str(vni_result[2][0])[:-3]

			if hop >= 3:
				#受信先デバイスID取得
				receive_device =  str(vni_result[hop][0])[:-3]
			elif hop == 2:
				return "This is StartPort"
			else:
				return "Non Route"
		except:
			return "DeviceID Parse Error"

		try:
			#受信先デバイス マネジメントIP取得
			sql = u"select * from device where did="+str(receive_device)
			receive_result = self.send_sql(sql)

			#送信開始/停止リクエスト送信
			send_url = "http://" + str(receive_result[0]["ipaddr"]) + ":3000/oam/lb/receive/" + str(vni)+"/"+str(hop)+"/"+str(sport)+"/"+str(dport)
			send_result = requests.get(send_url)
			print str(receive_result)
		except:
			pass

		try:
			if error == False:
				#送信先デバイス マネジメントIP取得
				sql = u"select * from device where did="+str(send_device)
				result = self.send_sql(sql)

				#送信開始/停止リクエスト送信
				send_url = "http://" + str(result[0]["ipaddr"]) + ":3000/oam/lb/send/" + str(vni)+"/"+str(mtu)+"/"+str(sport)+"/"+str(dport)
				send_result = requests.get(send_url)
				send_result = send_result.text.replace("{\n  \"result\": \"{'result': '",'').replace("'}\"\n}\n",'')
				send_url = "http://" + str(result[0]["ipaddr"]) + ":3000/oam/lb/stop/" + str(vni)
				send_stop_result = requests.get(send_url)
		except:
			pass

		send_url = "http://" + str(receive_result[0]["ipaddr"]) + ":3000/oam/lb/stop/" + str(vni)
		send_stop_result = requests.get(send_url)


		if error == True:
			return error_log
		else:
			return send_result

	'''
	def Add_Path_for_Local(self,start,end,vnipath,path):
		sql = "select * from device where did="+str(start)
		start_result = self.send_sql(sql)
		sql = "select * from device where did="+str(end)
		end_result = self.send_sql(sql)

		counter = 0
		while(True):
			if counter%2 == 0:
				path_type = "active"
			else:
				path_type = "standby"

			send_url = "http://" + str(start_result[0]["ipaddr"]) + ":3000/route_add/"+str(path[counter][0][0])[:-3]+"/"+str(path[counter][-1][0])[:-3]+"/"+str(vnipath[counter][0])+"/"+str(path_type)+"/"+str(path[counter])
			send_result = requests.get(send_url)
			if counter == 3:
				break
			counter+=1
		return 0
	'''


	def Delete_Path_for_Local(self,start,end):
		sql = "select * from device where did="+str(start)
		start_result = self.send_sql(sql)
		sql = "select * from device where did="+str(end)
		end_result = self.send_sql(sql)

		send_url = "http://" + str(start_result[0]["ipaddr"]) + ":3000/route_delete/"+str(start)+"/"+str(end)
		send_result = requests.get(send_url)
		return 0

	def Delete_Flow(self,start,end):
		global dpid_list
		sql = u"select * from flow_table where (start="+str(start)+" and end="+str(end)+") or (start="+str(end)+" and end="+str(start)+")"
		result = self.send_sql(sql)
		for data in result:
			datapath = dpid_list[data["dpid"]]
			ofp = datapath.ofproto
			ofp_parser = datapath.ofproto_parser
			match = ast.literal_eval(data["flow_match"].replace('OFPMatch(oxm_fields=','').replace(')',''))
			match = ofp_parser.OFPMatch(**match)
			tmp_dinfo = ast.literal_eval(data["actions"])
			dinfo={}
			dinfo["mode"]="flow_delete"
			dinfo["priority"] = tmp_dinfo["priority"]
			result = self.insert_flow(datapath,match,dinfo)

			sql = "select * from device where did="+str(data["dpid"])
			device_info = self.send_sql(sql)

			send_sql =  u"delete from flow_table where vni="+str(data["vni"])
			receive_url = "http://"+str(device_info[0]["ipaddr"])+":3000/sql/" + str(send_sql)
			receive_result = requests.get(receive_url)

		sql = u"delete from flow_table where (start="+str(start)+" and end="+str(end)+") or (start="+str(end)+" and end="+str(start)+")"
		result = self.send_sql(sql)
		return 0


def ws():
	api.run(host='0.0.0.0', port=3000)
webserver=threading.Thread(target=ws)
webserver.start()

#Localルート設定
@api.route('/route_search/<int:start>/<int:end>', methods=['GET'])
def route(start,end):
	me = Open_SDWAN()
	result,vnipath = me.route_search(start,end,0)
	if isinstance(result, str):
		result = {"result":str(result)}
	else:
		#addpath = me.Add_Path_for_Local(start,end,vnipath,result)
		if len(vnipath)  > 2:
			print len(vnipath)
			result = {
				"1st_route_1":"VNI:"+str(vnipath[0])+" Route:"+str(result[0]),
				"1st_route_2":"VNI:"+str(vnipath[2])+" Route:"+str(result[2]),
				"2nd_route_1":"VNI:"+str(vnipath[1])+" Route:"+str(result[1]),
				"2nd_route_2":"VNI:"+str(vnipath[3])+" Route:"+str(result[3])
				}
		else:
			result = {
				"1st_route_1":"VNI:"+str(vnipath[0])+" Route:"+str(result[0]),
				"1st_route_2":"VNI:"+str(vnipath[1])+" Route:"+str(result[1]),
				}
	return make_response(jsonify(result))

@api.route('/route_search/<int:start>/<int:end>/<string:custom_match>', methods=['GET'])
def route_custom(start,end,custom_match):
	me = Open_SDWAN()
	result,vnipath = me.route_search(start,end,custom_match)
	if isinstance(result, str):
		result = {"result":str(result)}
	else:
		#addpath = me.Add_Path_for_Local(start,end,vnipath,result)
		if len(vnipath)  > 2:
			print len(vnipath)
			result = {
				"1st_route_1":"VNI:"+str(vnipath[0])+" Route:"+str(result[0]),
				"1st_route_2":"VNI:"+str(vnipath[2])+" Route:"+str(result[2]),
				"2nd_route_1":"VNI:"+str(vnipath[1])+" Route:"+str(result[1]),
				"2nd_route_2":"VNI:"+str(vnipath[3])+" Route:"+str(result[3])
				}
		else:
			result = {
				"1st_route_1":"VNI:"+str(vnipath[0])+" Route:"+str(result[0]),
				"1st_route_2":"VNI:"+str(vnipath[1])+" Route:"+str(result[1]),
				}
	return make_response(jsonify(result))

#Localルート設定
@api.route('/route_delete/<int:start>/<int:end>', methods=['GET'])
def route_delete(start,end):
	me = Open_SDWAN()
	deleteflow = me.Delete_Flow(start,end)
	#deletepath = me.Delete_Path_for_Local(start,end)
	result = {"result":"complete"}
	return make_response(jsonify(result))

@api.route('/show/route/<int:start>/<int:end>', methods=['GET'])
def show_route(start,end):
	me = Open_SDWAN()
	sql = u"select vni,category,dpid from flow_table where start like '"+str(start*100)+"%' and end like '"+str(end*100)+"%' order by category asc"
	result = me.send_sql(sql)
	print sql
	sql = u"select vni,category,dpid from flow_table where start like '"+str(end*100)+"%' and end like '"+str(start*100)+"%' order by category asc"
	result2 = me.send_sql(sql)
	result = {"Outward":result},{"Homeward":result2}
	return make_response(jsonify(result))

@api.route('/show/route/<int:dpid>', methods=['GET'])
def show_dpid(dpid):
	me = Open_SDWAN()
	sql = u"select vni,category,start,end from flow_table where dpid="+str(dpid)+" order by category asc"
	result = me.send_sql(sql)
	result = {"result":result}
	return make_response(jsonify(result))


@api.route('/show/vni/<int:vni>', methods=['GET'])
def show_vni(vni):
	me = Open_SDWAN()
	sql = u"select start,end,category,dpid from flow_table where vni="+str(vni)+" order by category asc"
	result = me.send_sql(sql)
	result = {"result":result}
	return make_response(jsonify(result))

def show_vni(start,end):
	me = Open_SDWAN()
	sql = u"select vni,category,dpid from flow_table where start="+str(start)+" and end="+str(end)+" order by category asc"
	result = me.send_sql(sql)
	result = {"result":result}
	return make_response(jsonify(result))


@api.route('/oam/cc/start/<int:vni>', methods=['GET'])
def OAM_CC_Start(vni):
	me = Open_SDWAN()
	result = me.CC_Control(vni,"start")
	if isinstance(result, str):
		result = {"result":str(result)}
	else:
		result = {
			"result": str(result)
			}
	return make_response(jsonify(result))

@api.route('/oam/cc/stop/<int:vni>', methods=['GET'])
def OAM_CC_Stop(vni):
	me = Open_SDWAN()
	result = me.CC_Control(vni,"stop")
	if isinstance(result, str):
		result = {"result":str(result)}
	else:
		result = {
			"result": str(result)
			}
	return make_response(jsonify(result))

@api.route('/oam/lb/start/<int:vni>/<int:hop>/<int:mtu>/<int:sport>/<int:dport>', methods=['GET'])
def OAM_LB_Start(vni,hop,mtu,sport,dport):
	me = Open_SDWAN()
	result = me.LB_Control(vni,hop,mtu,sport,dport)
	if isinstance(result, str):
		result = {"result":str(result)}
	else:
		result = {
			"result": str(result)
			}
	return make_response(jsonify(result))

#Localルート設定
@api.route('/sql/<string:sql>', methods=['GET'])
def Get_SQL(sql):
	me = Open_SDWAN()
	result = me.send_sql(sql)

	result = {"result": "complete"}
	return make_response(jsonify(result))

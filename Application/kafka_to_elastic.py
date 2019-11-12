import time
import requests
import threading
import gc
from threading import Thread, BoundedSemaphore
from elasticsearch import Elasticsearch
from kafka import KafkaConsumer, KafkaProducer
import sys
args = sys.argv

threads=[]
pull_data=[]

def pulldt(pull_num,es):
	global pull_data
	while True:
		try:
			value=pull_data[int(pull_num)][0]
			pull_data[int(pull_num)].pop(0)
			value=value.rsplit(",")
			doc = {'received':str(value[1]),'sendtime':str(value[2]),'monitor':"alive",'minimum':str(value[3]),'jitter':str(value[4]),'serial':str(value[5]),'vxlanid':str(value[6])}
			tmp = es.index(index=value[0], doc_type='type1', body=doc)
		except:
			continue
def main():
	global threads
	global pull_data
	start_time=int(time.time())*1000
	consumer = KafkaConsumer(bootstrap_servers="<elastic_ip>:9092",auto_offset_reset="earliest",group_id="main",enable_auto_commit=True)
	consumer.subscribe(['oam-cc-data'+str(args[1])])

	for i in range(100):
		pull_data.append([])
		es = Elasticsearch(['<elastic_ip>'],http_auth=('elastic', 'changeme'),port=9200,timeout=999999999)
		thread_data=threading.Thread(target=pulldt,args=(str(i),es),name="a"+str(i))
		thread_data.start()

	num = 0
	while True:
		for message in consumer:
			if message.timestamp >= start_time:
				pull_data[int(num)].append(message.value)
				num=num+1
				if num == 100:
					num = 0

if __name__ == '__main__':
	main()
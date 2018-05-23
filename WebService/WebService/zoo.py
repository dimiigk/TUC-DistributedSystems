import json
import threading
from django.conf import settings
from kazoo.client import KazooClient
from kazoo.security import make_digest_acl


class Zooconf:
	connection = None
	storageServicesList = None
	authenticationServiceList = None

	def __init__(self):
		self.__zooConnect()
		self.__publishService()
		self.__initFsWatches()

	def __zooConnect(self):
		print("Connecting to ZooKeeper")
		self.connection = KazooClient(hosts=settings.ZOOKEEPER_HOST)
		self.connection.start()
		digest_auth = "%s:%s" % (settings.ZOOKEEPER_USER, settings.ZOOKEEPER_PASSWORD)
		self.connection.add_auth("digest", digest_auth)

	def __publishService(self):
		acl = make_digest_acl(settings.ZOOKEEPER_USER, settings.ZOOKEEPER_PASSWORD, all=True)
		dataJsonDict = {
			'SERVER_HOSTNAME': settings.SERVER_HOSTNAME,
			'SERVER_PORT': settings.SERVER_PORT,
			'CHILDREN': []
		}
		if self.connection.exists(path=settings.ZOOKEEPER_ROOT + settings.ZOOKEEPER_PATH_TO_NODE + settings.ZOOKEEPER_NODE_ID):
			self.connection.set(
				path=settings.ZOOKEEPER_ROOT + settings.ZOOKEEPER_PATH_TO_NODE + settings.ZOOKEEPER_NODE_ID,
				value=json.JSONEncoder().encode(dataJsonDict).encode()
			)
		else:
			self.connection.create_async(
				path=settings.ZOOKEEPER_ROOT + settings.ZOOKEEPER_PATH_TO_NODE + settings.ZOOKEEPER_NODE_ID,
				value=json.JSONEncoder().encode(dataJsonDict).encode(),
				ephemeral=settings.ZOOKEEPER_NODE_EPHIMERAL
			)
		if settings.ZOOKEEPER_PATH_TO_NODE != '':
			data, stat = self.connection.get(settings.ZOOKEEPER_ROOT + settings.ZOOKEEPER_PATH_TO_NODE)
			dataJsonDict = json.loads(data.decode("utf-8"))
			if settings.ZOOKEEPER_NODE_ID not in dataJsonDict['CHILDREN']:
				dataJsonDict['CHILDREN'].append(settings.ZOOKEEPER_NODE_ID)
			self.connection.set(
				path=settings.ZOOKEEPER_ROOT + settings.ZOOKEEPER_PATH_TO_NODE,
				value=json.JSONEncoder().encode(dataJsonDict).encode()
			)

	def __initFsWatches(self):
		# lists are supposed to be thread safe in python
		self.storageServicesList = []

		# Called immediately, and from then on
		@self.connection.ChildrenWatch(settings.ZOOKEEPER_ROOT + "fileservices")
		def watch_children(children):
			self.storageServicesList = []
			print("Children are now: %s" % children)
			for child in children:
				self.storageServicesList.append(child)

	def getAvailableFs(self): return self.storageServicesList

	def getZooConnection(self): return self.connection

	def getStatus(self):
		result = "{"
		try:
			rootChildren = self.connection.get_children(settings.ZOOKEEPER_ROOT)
			for child in rootChildren:
				data, stat = self.connection.get(settings.ZOOKEEPER_ROOT + child)
				result += '"' + child + '": ' + data.decode("utf-8") + ","
				try:
					grandchildren = self.connection.get_children(settings.ZOOKEEPER_ROOT + child)
					for grandchild in grandchildren:
						data, stat = self.connection.get(settings.ZOOKEEPER_ROOT + child + '/' + grandchild)
						result += '"' + grandchild + '": ' + data.decode("utf-8") + ","
					data, stat = self.connection.get(settings.ZOOKEEPER_ROOT + child + '/')
					dataJsonDict = json.loads(data.decode("utf-8"))
					dataJsonDict['CHILDREN'] = grandchildren
					self.connection.set(
						path=settings.ZOOKEEPER_ROOT + child,
						value=json.JSONEncoder().encode(dataJsonDict).encode()
					)
				except Exception:
					pass
			result = result[:-1] + '}'
			return json.loads(result)
		except Exception:
			self.__zooConnect()
			return self.getStatus()

	def getNodeData(self, node):
		status = self.getStatus()
		try:
			return status[node]
		except Exception:
			return {}

	def initZkTree(self):
		return

	def heartbeat(self):
		threading.Timer(300.0, self.heartbeat).start()
		print("Heartbeat")
		print(str(self.getStatus()))


zk = Zooconf()
zk.heartbeat()

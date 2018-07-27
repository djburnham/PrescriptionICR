__author__ = 'djb'
from pydocumentdb import document_client

CdbURI = 'https://prescription.documents.azure.com:443/'
CdbKey = 'K6GHrWUUBAFZ16yplZhcJdolISjtqaV0paoSZfv9omxs8rzXdRaVGrLpZGKuwlHvoS1AUC2S5myRoZ6KAEjnlQ=='
CdbID = 'prescriptionProcessing'

client = document_client.DocumentClient(CdbURI, {'masterKey': CdbKey})

db_query = "select * from r where r.id = '{0}'".format(CdbID)
db = list(client.QueryDatabases(db_query))[0]
db_link = db['_self']

coll_id = 'prescriptionItems'
coll_query = "select * from r where r.id = '{0}'".format(coll_id)
coll = list(client.QueryCollections(db_link, coll_query))[0]
coll_link = coll['_self']

query = { 'query': 'SELECT * FROM prescriptionItems p WHERE p.MEDICINAL_PRODUCT_NAME = "Cetirizine 10mg tablets" ' }
docs = client.QueryDocuments(coll_link, query)

resList = list(docs)
print list(docs)
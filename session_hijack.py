import avro.io, avro.schema, certifi, io, json, grpc, urllib3, requests, threading, time, pprint
import pubsub_api_pb2 as pb2
import pubsub_api_pb2_grpc as pb2_grpc
from credentials import client_id, client_secret, username, password

# globals
topic = "/event/LightningUriEventStream"
semaphore = threading.Semaphore(1)     # set a semaphore to keep the client running indefinitely
latest_replay_id = None                # Create a global variable to store the replay ID
instance_url = ''                      # to be used for API calls
access_token = ''                      # to be used for API calls

login_key_to_device_session_id = {}    # A <string>,<dict> dictionary to store all sessions encountered
schema = None                          # hold the schema so we don't retrieve it for each event separately
parsed_schema = None

def fetchReqStream(topic):
    global semaphore

    while True:
        semaphore.acquire()
        yield pb2.FetchRequest(
            topic_name = topic,
            replay_preset = pb2.ReplayPreset.LATEST,
            num_requested = 4) # represents the max we can process at one time. limit is 100.

def decode(schema_info, payload):
  global parsed_schema

  if not parsed_schema:
    parsed_schema = avro.schema.parse(schema_info)
  decoder = avro.io.BinaryDecoder(io.BytesIO(payload))
  reader = avro.io.DatumReader(parsed_schema)
  return reader.read(decoder)

def login():
    global client_id, client_secret, username, password

    login_endpoint = 'https://login.salesforce.com/services/oauth2/token'

    # Define the payload for the login request
    payload = {
        'grant_type': 'password',
        'client_id': client_id,
        'client_secret': client_secret,
        'username': username,
        'password': password
    }

    # Make the login request and get the access token
    response = requests.post(login_endpoint, data=payload)
    if response.status_code == 200:
        access_token = response.json().get('access_token')
        instance_url = response.json().get('instance_url')
        return(instance_url, access_token)
    else:
        print('Login failed. Response:', response.text)

def get_sessions(userid):
    global instance_url, access_token
    # returns a list of session IDs for the user
    query_path = '/services/data/v57.0/query?q=SELECT+Id+FROM+AuthSession+WHERE+UsersId+=+' + "'" + userid + "'"
    headers = {'Accept': 'application/json', 'Authorization': 'Bearer ' + access_token}
    res = requests.get(instance_url + query_path, headers=headers, verify=False)
    json_res =  json.loads(res.content)
    ret = []
    if 'records' in json_res:
        records = json_res['records']
        for record in records:
          ret.append(record['Id'])
    else:
        print('Response does not contain records: ' + str(json_res))
    return(ret)


def terminate_sessions(userid):
    global instance_url, access_token

    # use the composite API to delete all records in one action
    session_ids = get_sessions(userid)
    query_path = '/services/data/v57.0/composite/sobjects?ids='

    for sess in session_ids:
        query_path += (sess + ',')
    query_path = query_path[:-1]  # remove the final comma

    headers = {'Accept': 'application/json', 'Authorization': 'Bearer ' + access_token}
    res = requests.delete(instance_url + query_path, headers=headers, verify=False)
    if res.status_code != 200 and res.status_code != 404:
      print(res.status_code)
      print(res.content)

def process_events(evt):
    global login_key_to_device_session_id

    login_key = evt['LoginKey']
    device_session_id = evt['DeviceSessionId']
    user_id = evt['UserId']
    source_ip = evt['SourceIp']

    if login_key in login_key_to_device_session_id:
      original_device_session_id = login_key_to_device_session_id[login_key]['DeviceSessionId']
      if original_device_session_id != device_session_id:
        original_source_ip = login_key_to_device_session_id[login_key]['SourceIp']
        print(f'Session being used on more than one device -- terminating the session for user {user_id}, login_key {login_key}')
        print(f'\tOriginal Device Session ID: {original_device_session_id}. New Device Session ID: {device_session_id}')
        print(f'\tOriginal IP address: {original_source_ip}. New IP Address: {source_ip}')
        terminate_sessions(user_id)
        del login_key_to_device_session_id[login_key] # remove the login key since we terminated the sessions
    else:
      login_key_to_device_session_id[login_key] = { 'LoginKey' : login_key, 'UserId' : user_id, 'DeviceSessionId' : device_session_id, 'SourceIp' : source_ip }

def subscribe(access_token, instance_url, org_id):
    global latest_replay_id, schema

    auth_metadata = (('accesstoken', access_token),
    ('instanceurl', instance_url),
    ('tenantid', org_id))

    with open(certifi.where(), 'rb') as f:
        creds = grpc.ssl_channel_credentials(f.read())

    with grpc.secure_channel('api.pubsub.salesforce.com:7443', creds) as channel:
        stub = pb2_grpc.PubSubStub(channel)

        print(f"Subscribing to {topic}")
        substream = stub.Subscribe(fetchReqStream(topic), metadata=auth_metadata)
        for response in substream:
          if response.pending_num_requested == 0:
            semaphore.release()
          for e in response.events:
            payload_bytes = e.event.payload
            schema_id = e.event.schema_id
            if not schema: # This is an expensive call. Do it once and cache the schema to gain performance.
              schema_info = stub.GetSchema(pb2.SchemaRequest(schema_id=schema_id), metadata=auth_metadata).schema_json
            decoded_dict = decode(schema_info, payload_bytes)
            process_events(decoded_dict)
          else:
            print(f"[{time.strftime('%b %d, %Y %l:%M%p %Z')}] The subscription is active.")
          latest_replay_id = response.latest_replay_id

if __name__ == "__main__":
    # disable noisy warning message about certificate validation
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    instance_url, access_token = login()
    org_id = access_token.split('!')[0]

    subscribe(access_token, instance_url, org_id)

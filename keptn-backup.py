import boto3
import os
import shutil
import base64
import tarfile
from datetime import datetime
from kubernetes import client, config
from kubernetes.stream import stream


def get_keptn_instances():
    print("Searching for keptn instances...")

    keptn = []
    configservice_pod = ""
    mongodb_pod = ""

    api_instance = client.CoreV1Api()
    namespaces = api_instance.list_namespace()
    for namespace in namespaces.items:        
        pods = api_instance.list_namespaced_pod(namespace.metadata.name)
        addtolist = False
        for pod in pods.items:
            try:
                label = pod.metadata.labels['app.kubernetes.io/name']
                if label == "configuration-service":
                    print("Found keptn in " + namespace.metadata.name + " " + pod.metadata.name)
                    configservice_pod = pod.metadata.name
                    addtolist = True
                if label == "mongodb":
                    print("Found mongodb in " + namespace.metadata.name + " " + pod.metadata.name)                    
                    mongodb_pod = pod.metadata.name
                    addtolist = True
            except KeyError:
                next
        
        if addtolist:
            if configservice_pod != "" and mongodb_pod != "":
                keptn.append({
                    "name": namespace.metadata.name,
                    "configuration-service": configservice_pod,
                    "mongodb-datastore": mongodb_pod,
                })
    return keptn
                
def git_backup(instance):
    # kubectl cp keptn/$CONFIG_SERVICE_POD:/data ./config-svc-backup/ -c configuration-service
    print("Backup GIT Repositories from " + instance['configuration-service'])
    os.system("kubectl cp "+instance['name']+"/"+instance['configuration-service']+":/data ./"+instance['name']+"/configuration-service/ -c configuration-service")

def mongodb_backup(instance):
    print("Backup mongodb-datastore")
    v1 = client.CoreV1Api()
    secret = v1.read_namespaced_secret("mongodb-credentials", instance['name'])
    admin_pass = base64.b64decode(secret.data['admin_password']).decode("utf-8")
    password = base64.b64decode(secret.data['password']).decode("utf-8")
    user = base64.b64decode(secret.data['user']).decode("utf-8")

    os.system("kubectl exec svc/mongodb -n "+instance['name']+" -- mongodump --uri=\"mongodb://user:"+password+"@localhost:27017/keptn\" --out=./dump")
    os.system("kubectl cp "+instance['name']+"/"+instance['mongodb-datastore']+":dump ./"+instance['name']+"/mongodb-datastore/ -c mongodb")

def secrets_backup(instance):
    print("Dumping git credentials")
    v1 = client.CoreV1Api()
    secrets = v1.list_namespaced_secret(instance['name'])
    for secret in secrets.items:
        if secret.metadata.name.startswith("git-credentials-"):
            os.system("kubectl get secret -n "+instance['name']+" "+secret.metadata.name+" -o yaml > ./"+instance['name']+"/secrets/"+secret.metadata.name+".yaml")            

def create_archive(instance):
    
    filename = instance['name']+"_"+datetime.now().strftime("%Y-%m-%d-%H_%M_%S")+".tar.gz"
    with tarfile.open(filename, "w:gz") as tar:
        tar.add(instance['name'], arcname=os.path.basename(instance['name']))
    return filename

def upload_to_s3(filename, instance):
    print("Upload archive " + filename + " to Bucket...")
    SECRET_ACCESS_KEY = os.getenv('SECRET_ACCESS_KEY')
    ACCESS_KEY_ID = os.getenv('ACCESS_KEY_ID')
    ENDPOINT_URL = os.getenv('ENDPOINT_URL')    

    session = boto3.session.Session()
    client = session.client('s3',
                            endpoint_url=ENDPOINT_URL,
                            aws_access_key_id=ACCESS_KEY_ID,
                            aws_secret_access_key=SECRET_ACCESS_KEY)

    client.upload_file(filename,
                    instance['name'],
                    filename)

def create_backup():    
    instances = get_keptn_instances()   
    
    for instance in instances:
        # Create temporary instance folder
        if not run_in_cluster:
            try:
                shutil.rmtree(instance['name'])
            except:
                print("Deletion of the directory "+instance['name']+" failed")

        os.makedirs(instance['name']+"/configuration-service")
        os.makedirs(instance['name']+"/mongodb-datastore")
        os.makedirs(instance['name']+"/secrets")
        git_backup(instance)
        mongodb_backup(instance)
        secrets_backup(instance)
        archive = create_archive(instance)
        upload_to_s3(archive, instance)    
        
    
def main():
    print('Keptn Backup Utility')
    create_backup()

run_in_cluster = False
if os.getenv("KUBERNETES_SERVICE_PORT") is None:
    print("Running outside of the cluster")
    config.load_kube_config()
else:
    # Running inside the cluster
    run_in_cluster = True
    print("Running within the cluster")
    config.load_incluster_config()


if __name__ == "__main__":
    main()
import boto3
import os
import shutil
import base64
import tarfile
from datetime import datetime
from kubernetes import client, config
from kubernetes.stream import stream

if not "SECRET_ACCESS_KEY" in os.environ:
    print("Missing env-var SECRET_ACCESS_KEY")
    exit(1)
if not "ACCESS_KEY_ID" in os.environ:
    print("Missing env-var ACCESS_KEY_ID")
    exit(1)
if not "ENDPOINT_URL" in os.environ:
    print("Missing env-var ENDPOINT_URL")
    exit(1)
if not "KEPTN_INSTANCE" in os.environ:
    print("Missing env-var KEPTN_INSTANCE")
    exit(1)
if not "BACKUP_ARCHIVE" in os.environ:
    print("Missing env-var BACKUP_ARCHIVE")
    exit(1)            

SECRET_ACCESS_KEY = os.getenv('SECRET_ACCESS_KEY')
ACCESS_KEY_ID = os.getenv('ACCESS_KEY_ID')
ENDPOINT_URL = os.getenv('ENDPOINT_URL')    
KEPTN_INSTANCE =  os.getenv('KEPTN_INSTANCE')
BACKUP_ARCHIVE =  os.getenv('BACKUP_ARCHIVE')

def get_keptn_instances():
    print("Searching for keptn instances...")

    keptn = []
    configservice_pod = ""
    mongodb_pod = ""

    api_instance = client.CoreV1Api()
      
    pods = api_instance.list_namespaced_pod(KEPTN_INSTANCE)
    addtolist = False
    for pod in pods.items:
        try:
            label = pod.metadata.labels['app.kubernetes.io/name']
            if label == "configuration-service":
                print("Found keptn in " + KEPTN_INSTANCE + " " + pod.metadata.name)
                configservice_pod = pod.metadata.name
                addtolist = True
            if label == "mongodb":
                print("Found mongodb in " + KEPTN_INSTANCE + " " + pod.metadata.name)                    
                mongodb_pod = pod.metadata.name
                addtolist = True
        except KeyError:
            next
    
    if addtolist:
        if configservice_pod != "" and mongodb_pod != "":
            keptn.append({
                "name": KEPTN_INSTANCE,
                "configuration-service": configservice_pod,
                "mongodb": mongodb_pod,
            })
    return keptn

def download_backup():
    # https://keptn.fra1.digitaloceanspaces.com/keptn-02/keptn-02_2021-04-08-13_38_37.tar.gz
    session = boto3.session.Session()
    client = session.client('s3',
                            endpoint_url=ENDPOINT_URL,
                            aws_access_key_id=ACCESS_KEY_ID,
                            aws_secret_access_key=SECRET_ACCESS_KEY)
    
    print('Download backup...')
    #print(BACKUP_ARCHIVE)
    #print(KEPTN_INSTANCE)
    #print(ENDPOINT_URL)

    client.download_file(KEPTN_INSTANCE,
                    BACKUP_ARCHIVE,
                    BACKUP_ARCHIVE)
    return

def extract_backup():
    print("Extract archive...")
    tar = tarfile.open(BACKUP_ARCHIVE)
    tar.extractall()
    tar.close()
    return

def restore_git(configuration_service_pod):
    print("Copy configuration service files to pod " + configuration_service_pod)
    os.system("kubectl -n "+KEPTN_INSTANCE+" cp ./"+KEPTN_INSTANCE+"/configuration-service/* "+configuration_service_pod+":/data -c configuration-service")
    
    print("Upload reset script to pod " + configuration_service_pod)
    os.system("kubectl -n "+KEPTN_INSTANCE+" cp ./reset-git-repos.sh "+configuration_service_pod+":/ -c configuration-service")
    
    print("Resetting git repositories")
    os.system("kubectl exec -n "+KEPTN_INSTANCE+" "+configuration_service_pod+" -c configuration-service -- chmod +x -R ./reset-git-repos.sh")
    os.system("kubectl exec -n "+KEPTN_INSTANCE+" "+configuration_service_pod+" -c configuration-service -- ./reset-git-repos.sh")
    return

def restore_mongodb(mongodb_pod):
    print("Restoring mongodb")
    print("Upload backup to pod "+mongodb_pod)    
    os.system("kubectl -n "+KEPTN_INSTANCE+" cp ./"+KEPTN_INSTANCE+"/mongodb-datastore/ "+mongodb_pod+":dump -c mongodb")
    
    v1 = client.CoreV1Api()
    secret = v1.read_namespaced_secret("mongodb-credentials", KEPTN_INSTANCE)
    admin_pass = base64.b64decode(secret.data['admin_password']).decode("utf-8")
    password = base64.b64decode(secret.data['password']).decode("utf-8")
    user = base64.b64decode(secret.data['user']).decode("utf-8")

    os.system("kubectl exec svc/mongodb -n "+KEPTN_INSTANCE+" -- mongorestore --host localhost:27017 --username user --password "+password+" --authenticationDatabase keptn ./dump")
    return

def restore_git_credentials():
    for filename in os.listdir("./"+KEPTN_INSTANCE+"/secrets/"):
        if filename.endswith(".yaml"):
            file = os.path.join("./"+KEPTN_INSTANCE+"/secrets/",filename)
            os.system("kubectl -n "+KEPTN_INSTANCE+" apply -f "+file)
        else:
            continue    
    return

def main():
    print('Keptn Restore Utility')
    download_backup()
    extract_backup()
    instance = get_keptn_instances()
    print(instance[0]["mongodb"])
    print(instance[0]["configuration-service"])
    restore_git(instance[0]["configuration-service"])
    restore_mongodb(instance[0]["mongodb"])
    restore_git_credentials()

    

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
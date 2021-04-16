# Keptn Backup Utility

## Introduction

With this utility, you can backup all Keptn installations on your cluster and upload the backup to an S3 compatible object store.

Steps:

- Scanning namespaces to find all Keptn Installations
- Backup of the GIT repositories within the configuration-service
- Dumping MongoDB data
- Backup of git-credential secrets
- Create a backup archive
- Upload archive to an object store

_Please note: This is a preview version and is not ready for production!_

## Backup Keptn

You can either run this tool as a single docker container from any host (kubeconfig file with a single context needed), or run it within your Kubernetes Cluster as an ad-hoc container as well as a cronjob.

### Setup

Create a keptn-backup namespace and a service account within your cluster, and bind a cluster-admin role to the service account (todo: create RBAC role with fewer privileges).

```
kubectl create ns keptn-backup
kubectl create serviceaccount keptn-backup --namespace keptn-backup

cat <<EOT >> keptn-backup-rolebinding.yaml
kind: ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1beta1
metadata:
  name: keptn-backup-clusterrolebinding
subjects:
- kind: ServiceAccount
  name: keptn-backup
  namespace: keptn-backup
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: ""
EOT

kubectl apply -n keptn-backup -f keptn-backup-rolebinding.yaml
```
### Execute ad-hoc backup

Run the following command to create a backup of all your Keptn instances.

```
kubectl run --rm -i --tty keptn-backup -n keptn-backup \
  --image=checkelmann/keptn-backup:latest \
  --env="SECRET_ACCESS_KEY=BUCKET_SECRET_ACCESS_KEY" \
  --env="ACCESS_KEY_ID=BUCKET_ACCESS_KEY_ID" \
  --env="ENDPOINT_URL=https://BUCKET_ENDPOINT_URL/" \
  --restart=Never --serviceaccount=keptn-backup
```

### Run as a cronjob

Create a secret called `backup-secret` containing your SECRET_ACCESS_KEY, ACCESS_KEY_ID, and ENDPOINT_URL within the keptn-backup namespace.

```
apiVersion: v1
kind: Secret
metadata:
  name: backup-secret
  namespace: keptn-backup
data:
  ACCESS_KEY_ID: BASE64ENCODED_ACCESS_KEY_ID
  ENDPOINT_URL: BASE64ENCODED_ENDPOINT_URL
  SECRET_ACCESS_KEY: BASE64ENCODED_SECRET_ACCESS_KEY
type: Opaque
```
Create the secret within keptn-backup namespace.

```
kubectl apply -n keptn-backup -f secret.yaml
```

Create a cronjob which is running every day at 1AM

```
apiVersion: batch/v1beta1
kind: CronJob
metadata:
  name: backup-keptn
spec:
  schedule: "* 1 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: keptn-backup
          containers:
          - name: backup-keptn
            image: checkelmann/keptn-backup:latest
            envFrom:
            - secretRef:
                name: backup-secret
          restartPolicy: OnFailure
```

## Restore Keptn

To restore a specific Keptn installation, run the following command.

Additional Parameters:
- KEPTN_INSTANCE = Namespace of your Keptn Installation to recover (should be the same as the original namespace)
- BACKUP_ARCHIVE = The backup archive filename within the object store

```
kubectl run --rm -i --tty keptn-restore -n keptn-backup \
 --image=checkelmann/keptn-restore:latest \
 --env="SECRET_ACCESS_KEY=SECRET_ACCESS_KEY" \
 --env="ACCESS_KEY_ID=ACCESS_KEY_ID" \
 --env="ENDPOINT_URL=https://ENDPOINT_URL/" \
 --env="KEPTN_INSTANCE=keptn" \
 --env="BACKUP_ARCHIVE=keptn_TIMESTAMP.tar.gz" \
 --restart=Never --serviceaccount=keptn-backup
```
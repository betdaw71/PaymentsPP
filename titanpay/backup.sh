#!/bin/bash

POSTGRES_DB=jXCPa9JbvIX673isqdpX
POSTGRES_USER=9W5Ft55t67Rh2nbkYLVG
POSTGRES_CONTAINER=pg

# Local backup directory
LOCAL_BACKUP_DIR=/var/www/backup

# Backup file names
BACKUP_FILE=db-backup-$(date +%F).sql
ENCRYPTED_BACKUP_FILE=db-backup-$(date +%F).sql.enc

# Encryption key (replace with your actual key)
ENCRYPTION_KEY=your_encryption_key

# Create a backup
docker exec $POSTGRES_CONTAINER pg_dump -U $POSTGRES_USER $POSTGRES_DB > $LOCAL_BACKUP_DIR/$BACKUP_FILE
docker exec pg pg_dump -U 9W5Ft55t67Rh2nbkYLVG jXCPa9JbvIX673isqdpX > /db-backup-1.sql.enc
# Encrypt the backup
openssl enc -aes-256-cbc -salt -in $LOCAL_BACKUP_DIR/$BACKUP_FILE -out $LOCAL_BACKUP_DIR/$ENCRYPTED_BACKUP_FILE -pass pass:$ENCRYPTION_KEY

# (Optional) Remove the unencrypted backup file
rm $LOCAL_BACKUP_DIR/$BACKUP_FILE

# (Optional) FTP server details for transferring the backup
FTP_HOST=st-e.server-panel.net
FTP_USER=user4772875
FTP_PASSWORD=xqCMExJMmb1E
FTP_REMOTE_DIR=/backups

# (Optional) Upload the encrypted backup to the FTP server
curl -T $LOCAL_BACKUP_DIR/$ENCRYPTED_BACKUP_FILE ftp://$FTP_USER:$FTP_PASSWORD@$FTP_HOST/$FTP_REMOTE_DIR/

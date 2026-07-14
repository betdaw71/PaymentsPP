echo ====MIGRATING [START]====
python manage.py migrate
echo ====MIGRATING [END]====

echo ====LOADING DATA [START]====
python manage.py initadmin
python manage.py genbase
echo ====LOADING DATA [END]====

echo ====STARTING CRON====

touch /var/log/cron.log
printenv | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID|LANG|PWD|GPG_KEY|_=' >> /etc/environment

python manage.py crontab remove
python manage.py crontab add
service cron start


echo ====RUNNING [START]====
python manage.py runserver 0.0.0.0:8080 --noreload
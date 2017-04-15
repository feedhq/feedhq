from   base
env    DEBIAN_FRONTEND noninteractive

run    dpkg-divert --local --rename --add /sbin/initctl
run    ln -s /bin/true /sbin/initctl

run    apt-get install -y -q software-properties-common
run    add-apt-repository -y "deb http://archive.ubuntu.com/ubuntu $(lsb_release -sc) universe"
run    add-apt-repository -y "deb http://apt.postgresql.org/pub/repos/apt/ precise-pgdg main"
run    apt-get --yes update
run    apt-get --yes upgrade --force-yes

# Basic Requirements
run     apt-get -y --force-yes install curl git wget unzip supervisor \
            postgresql-9.3 redis-server python-setuptools \
            python-pip libpq-dev gunicorn python-dev libxml2-dev libxslt-dev


add   . /srv
run    cd /srv; python setup.py develop

expose 80

cmd ["/bin/bash"]
# coding: utf-8
from __future__ import unicode_literals, print_function
import sys
import pwd
import time
import re
import os
import socket
from sqlalchemy import distinct
from oar.lib import (db, config, get_logger, Resource, AssignedResource)

from oar.lib.compat import is_py2

if is_py2:
    from subprocess32 import (Popen, call, PIPE, TimeoutExpired)
else:
    from subprocess import (Popen, call, PIPE, TimeoutExpired)  # noqa

logger = get_logger("oar.lib.tools")

almighty_socket = None

notification_user_socket = None


def init_judas_notify_user():  # pragma: no cover

    logger.debug("init judas_notify_user (launch judas_notify_user.pl)")

    global notify_user_socket
    uds_name = "/tmp/judas_notify_user.sock"
    if not os.path.exists(uds_name):
        binary = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                              "judas_notify_user.pl")
        os.system("%s &" % binary)

        while(not os.path.exists(uds_name)):
            time.sleep(0.1)

        notification_user_socket = socket.socket(
            socket.AF_UNIX, socket.SOCK_STREAM)
        notification_user_socket.connect(uds_name)


def notify_user(job, state, msg):  # pragma: no cover
    global notification_user_socket
    # Currently it uses a unix domain sockey to communication to a perl script
    # TODO need to define and develop the next notification system
    # see OAR::Modules::Judas::notify_user

    logger.debug("notify_user uses the perl script: judas_notify_user.pl !!! ("
                 + state + ", " + msg + ")")

    # OAR::Modules::Judas::notify_user($base,notify,$addr,$user,$jid,$name,$state,$msg);
    # OAR::Modules::Judas::notify_user($dbh,$job->{notify},$addr,$job->{job_user},$job->{job_id},$job->{job_name},"SUSPENDED","Job
    # is suspended."
    addr, port = job.info_type.split(':')
    msg_uds = job.notify + "°" + addr + "°" + job.user + "°" + job.id + "°" +\
        job.name + "°" + state + "°" + msg + "\n"
    nb_sent = notification_user_socket.send(msg_uds)

    if nb_sent == 0:
        logger.error("notify_user: socket error")


def create_almighty_socket():  # pragma: no cover
    global almighty_socket
    almighty_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server = config["SERVER_HOSTNAME"]
    port = config["SERVER_PORT"]
    try:
        almighty_socket.connect((server, port))
    except socket.error as exc:
        logger.error("Connection to Almighty" + server + ":" + str(port) +
                     " raised exception socket.error: " + str(exc))
        sys.exit(1)


# TODO: refactor to use zmq
def notify_almighty(message):  # pragma: no cover
    if not almighty_socket:
        create_almighty_socket()
    return almighty_socket.send(message)


# TODO: refactor to use zmq
def notify_tcp_socket(addr, port, message):  # pragma: no cover
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    logger.debug('notify_tcp_socket:' + addr + ":" + port + ', msg:' + message)
    try:
        tcp_socket.connect((addr, int(port)))
    except socket.error as exc:
        logger.error("notify_tcp_socket: Connection to " + addr + ":" + port +
                     " raised exception socket.error: " + str(exc))
        return 0
    nb_sent = tcp_socket.send(message)
    tcp_socket.close()
    return nb_sent



#TODO
def signal_oarexec(host, job_id, signal, wait, ssh_cmd, user_signal):
    return 0
## Send the given signal to the right oarexec process
## args : host name, job id, signal, wait or not (0 or 1), 
## DB ref (to close it in the child process), ssh cmd, user defined signal 
## for oardel -s (null by default if not used)
## return an array with exit values
#sub signal_oarexec($$$$$$$){
#    my $host = shift;
#    my $job_id = shift;
#    my $signal = shift;
#    my $wait = shift;
#    my $base = shift;
#    my $ssh_cmd = shift;
#    my $user_signal = shift;
#
#    my $file = get_oar_pid_file_name($job_id);
#    #my $cmd = "$ssh_cmd -x -T $host \"test -e $file && cat $file | xargs kill -s $signal\"";
#    #my $cmd = "$ssh_cmd -x -T $host bash -c \"test -e $file && PROC=\\\$(cat $file) && kill -s CONT \\\$PROC && kill -s $signal \\\$PROC\"";
#    my ($cmd_name,@cmd_opts) = split(" ",$ssh_cmd);
#    my @cmd;
#    my $c = 0;
#    $cmd[$c] = $cmd_name;$c++;
#    foreach my $p (@cmd_opts){
#        $cmd[$c] = $p;$c++;
#    }
#    $cmd[$c] = "-x";$c++;
#    $cmd[$c] = "-T";$c++;
#    $cmd[$c] = $host;$c++;
#    if (defined($user_signal) && $user_signal ne ''){
#        my $signal_file = OAR::Tools::get_oar_user_signal_file_name($job_id);
#	    $cmd[$c] = "bash -c 'echo $user_signal > $signal_file && test -e $file && PROC=\$(cat $file) && kill -s CONT \$PROC && kill -s $signal \$PROC'";$c++;
#    }
#    else {
#    	$cmd[$c] = "bash -c 'test -e $file && PROC=\$(cat $file) && kill -s CONT \$PROC && kill -s $signal \$PROC'";$c++;
#    }
#    $SIG{PIPE}  = 'IGNORE';
#    my $pid = fork();
#    if($pid == 0){
#        #CHILD
#        undef($base);
#        my $exit_code;
#        my $ssh_pid;
#        eval{
#            $SIG{PIPE}  = 'IGNORE';
#            $SIG{ALRM} = sub { die "alarm\n" };
#            alarm(get_ssh_timeout());
#            $ssh_pid = fork();
#            if ($ssh_pid == 0){
#                exec({$cmd_name} @cmd);
#                warn("[ERROR] Cannot find @cmd\n");
#                exit(-1);
#            }
#            my $wait_res = -1;
#            # Avaoid to be disrupted by a signal
#            while ((defined($ssh_pid)) and ($wait_res != $ssh_pid)){
#                $wait_res = waitpid($ssh_pid,0);
#            }
#            alarm(0);
#            $exit_code  = $?;
#        };
#        if ($@){
#            if ($@ eq "alarm\n"){
#                if (defined($ssh_pid)){
#                    my ($children,$cmd_name) = get_one_process_children($ssh_pid);
#                    kill(9,@{$children});
#                }
#            }
#        }
#        # Exit from child
#        exit($exit_code);
#    }
#    if ($wait > 0){
#        waitpid($pid,0);
#        my $exit_value  = $? >> 8;
#        my $signal_num  = $? & 127;
#        my $dumped_core = $? & 128;
#
#        return($exit_value,$signal_num,$dumped_core);
#    }else{
#        return(undef);
#    }
#}
#
#

# get_date
# returns the current time in the format used by the sql database


def get_date():

    if db.engine.dialect.name == 'sqlite':
        req = "SELECT strftime('%s','now')"
    else:   # pragma: no cover
        req = "SELECT EXTRACT(EPOCH FROM current_timestamp)"

    result = db.session.execute(req).scalar()
    return int(result)


# sql_to_local
# converts a date specified in the format used by the sql database to an
# integer local time format
# parameters : date string
# return value : date integer
# side effects : /


def sql_to_local(date):
    # Date "year mon mday hour min sec"
    date = ' '.join(re.findall(r"[\d']+", date))
    t = time.strptime(date, "%Y %m %d %H %m %s")
    return int(time.mktime(t))


# local_to_sql
# converts a date specified in an integer local time format to the format used
# by the sql database
# parameters : date integer
# return value : date string
# side effects : /

def local_to_sql(local):
    return time.strftime("%F %T", time.localtime(local))

# sql_to_hms
# converts a date specified in the format used by the sql database to hours,
# minutes, secondes values
# parameters : date string
# return value : hours, minutes, secondes
# side effects : /


def sql_to_hms(t):
    hms = t.split(':')
    return (hms[0], hms[1], hms[2])

# hms_to_sql
# converts a date specified in hours, minutes, secondes values to the format
# used by the sql database
# parameters : hours, minutes, secondes
# return value : date string
# side effects : /


def hms_to_sql(hour, min, sec):

    return(str(hour) + ":" + str(min) + ":" + str(sec))
# hms_to_duration
# converts a date specified in hours, minutes, secondes values to a duration
# in seconds
# parameters : hours, minutes, secondes
# return value : duration
# side effects : /


def hms_to_duration(hour, min, sec):
    return int(hour) * 3600 + int(min) * 60 + int(sec)


# duration_to_hms
# converts a date specified as a duration in seconds to hours, minutes,
# secondes values
# parameters : duration
# return value : hours, minutes, secondes
# side effects : /


def duration_to_hms(t):

    sec = t % 60
    t /= 60
    min = t % 60
    hour = int(t / 60)

    return (hour, min, sec)

# duration_to_sql
# converts a date specified as a duration in seconds to the format used by the
# sql database
# parameters : duration
# return value : date string
# side effects : /


def duration_to_sql(t):

    hour, min, sec = duration_to_hms(t)

    return hms_to_sql(hour, min, sec)


# sql_to_duration
# converts a date specified in the format used by the sql database to a
# duration in seconds
# parameters : date string
# return value : duration
# side effects : /

def sql_to_duration(t):
    (hour, min, sec) = sql_to_hms(t)
    return hms_to_duration(hour, min, sec)


def send_checkpoint_signal(job):
    logger.debug("Send checkpoint signal to the job " + str(job.id))
    logger.warning("Send checkpoint signal NOT YET IMPLEMENTED ")
    # Have a look to  check_jobs_to_kill/oar_meta_sched.pl

def get_username(): # NOTUSED
    return pwd.getpwuid( os.getuid() ).pw_name

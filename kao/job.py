from oar import db, Job, MoldableJobDescription, JobResourceDescription, JobResourceGroup, Resource
from oar import GanttJobsPrediction, GanttJobsResource, MoldableJobDescription
from interval import unordered_ids2itvs, itvs2ids
class Job(Job):
    ''' Use 

        j1 = Job(1,"Waiting", 0, 0, "yop", "", "",{}, [], 0, 
                 [ 
                     (1, 60, 
                      [  ( [("node", 2)], [(1,32)] )  ]
                  )
                 ]         
        )

    Attributes:

    mld_res_rqts: Resources requets by moldable instance
                  [                                    # first moldable instance
                     (1, 60,                           # moldable id, walltime 
                      [  ( [("node", 2)], [(1,32)] ) ] # list of requests composed of
                  )                                    # list of hierarchy request and filtered 
                 ]                                     # resources (Properties)
    

    '''

    def pseudo(self, start_time, walltime, res_set):
        self.start_time = start_time
        self.walltime = walltime
        self.res_set = res_set
        
    def set(self, id, state, start_time, walltime, user, name, project, types, res_set, \
                 moldable_id, mld_res_rqts, key_cache=""):
        self.id = id
        self.state = state
        self.start_time = start_time
        self.walltime = walltime
        self.user = user
        self.name = name
        self.project = project
        self.types = types
        self.res_set = res_set
        self.moldable_id = moldable_id
        self.mld_res_rqts = mld_res_rqts #[ (moldable_id, walltime, 
        #                                   [   [ (hy_level, hy_nb, constraints) ]  ]
        # hy_level = [ [string] ]
        # hy_nb = [ [ int ] ]
        # constraints = [ [itvs]  ]
        self.key_cache = key_cache
        if not key_cache:
            if len(mld_res_rqts) == 1:
                (m_id, walltime, res_rqt) = mld_res_rqts[0]
                self.key_cache = (str(walltime)).join(str(res_rqt))
            else:
                #TODO cache for moldable_id
                pass

def get_waiting_jobs(queue):
    #TODO  fairsharing_nb_job_limit
    waiting_jobs = {}
    waiting_jids = []   
    nb_waiting_jobs = 0

    for j in Job.query.filter(Job.state == "Waiting")\
                      .filter(Job.queue_name == queue)\
                      .filter(Job.reservation == 'None'):
        jid = int(j.id)
        waiting_jobs[jid] = j
        waiting_jids.append(jid)
        nb_waiting_jobs += 1

    return (waiting_jobs, waiting_jids, nb_waiting_jobs)
        

def get_data_jobs(jobs, jids, resource_set):
    '''
    oarsub -q test -l "nodes=1+{network_address='node3'}/nodes=1/resource_id=1" sleep
    job_id: 12 [(16L, 7200, [([(u'network_address', 1)], [(0, 7)]), ([(u'network_address', 1), (u'resource_id', 1)], [(4, 7)])])]

    '''

    req = db.query(Job.id,\
                   MoldableJobDescription.id,\
                   MoldableJobDescription.walltime,\
                   JobResourceGroup.res_group_id,\
                   JobResourceGroup.res_group_moldable_id,\
                   JobResourceGroup.res_group_property,\
                   JobResourceDescription.res_job_group_id,\
                   JobResourceDescription.res_job_resource_type,\
                   JobResourceDescription.res_job_value)\
            .filter(MoldableJobDescription.index == 'CURRENT')\
            .filter(JobResourceGroup.res_group_index == 'CURRENT')\
            .filter(JobResourceDescription.res_job_index == 'CURRENT')\
            .filter(Job.id.in_( tuple(jids) ))\
            .filter(Job.id == MoldableJobDescription.job_id)\
            .filter(JobResourceGroup.res_group_moldable_id == MoldableJobDescription.id)\
            .filter(JobResourceDescription.res_job_group_id == JobResourceGroup.res_group_id)\
            .order_by(MoldableJobDescription.id,JobResourceGroup.res_group_id,\
                      JobResourceDescription.res_job_group_id,\
                      JobResourceDescription.res_job_order)\
            .all()

    cache_constraints = {}

    first_job = True
    prev_j_id = 0
    prev_mld_id = 0
    prev_jrg_id = 0
    prev_res_jrg_id = 0
    mld_res_rqts = []
    jrg = []
    jr_descriptions = []
    
    for x in req:
        j_id, mld_id, mld_id_walltime, jrg_id, jrg_mld_id, jrg_grp_property, res_jrg_id, res_type, res_value = x #remove res_order
        #print  x
        #
        # new job 
        #
        if j_id != prev_j_id:
            if first_job:
                first_job = False
            else:
                jrg.append( (jr_descriptions, res_constraints) )
                mld_res_rqts.append( (prev_mld_id, prev_mld_id_walltime, jrg) )
                job.mld_res_rqts = mld_res_rqts
                job.types = {} #TODO
                job.key_cache = str(mld_res_rqts)
                mld_res_rqts = []
                jrg = []
                jr_descriptions = []
                #print "======================"
                #print "job_id:",job.id,  job.mld_res_rqts
                #print "======================"

            prev_mld_id = mld_id
            prev_mld_id_walltime = mld_id_walltime
            prev_j_id = j_id
            job = jobs[j_id]

        else:
            #
            # new moldable_id
            #

            if mld_id != prev_mld_id:
                if jrg != []:
                    jrg.append( (jr_descriptions, res_constraints) )
                    mld_res_rqts.append( (prev_mld_id, prev_mld_id_walltime, jrg) )
                
                prev_mld_id = mld_id
                prev_mld_id_walltime = mld_id_walltime 
                jrg = []
                jr_descriptions = []
        #
        # new job resources groupe_id
        #
        if jrg_id != prev_jrg_id:
            prev_jrg_id = jrg_id
            if jr_descriptions != []:
                jrg.append( (jr_descriptions, res_constraints) )
                jr_descriptions = []

        #
        # new set job descriptions
        #
        if res_jrg_id != prev_res_jrg_id:
            prev_res_jrg_id = res_jrg_id
            jr_descriptions = [ (res_type, res_value) ]

            #
            # determine resource constraints
            #
            if ( job.properties == "" and ( jrg_grp_property == "" or jrg_grp_property == "type = 'default'" ) ):
                res_constraints = resources_set.roid_itvs
            else:
                if job.properties == "" or  jrg_grp_property == "":
                    and_sql = ""
                else:
                    and_sql = " AND "
            
                sql_constraints = job.properties + and_sql + jrg_grp_property
                    
                if sql_constraints in cache_constraints:
                    res_constraints = cache_constraints[sql_constraints]
                else:
                    request_constraints = db.query(Resource.id).filter(sql_constraints).all()
                    roids = [ resource_set.rid_i2o[ int(y[0]) ] for y in request_constraints ]
                    res_constraints = unordered_ids2itvs(roids)
                    cache_constraints[sql_constraints] = res_constraints
        else:
            # add next res_type , res_value
            jr_descriptions.append( (res_type, res_value) )
            #print "@@@@@@@@@@@@@@@@@@@"
            #print jr_descriptions

    # complete the last job
    jrg.append( (jr_descriptions, res_constraints) )
    mld_res_rqts.append( (prev_mld_id, prev_mld_id_walltime, jrg ) )
    job.mld_res_rqts = mld_res_rqts
    job.types = {} #TODO
    job.key_cache = str(mld_res_rqts)

    #print "======================"
    #print "job_id:",job.id,  job.mld_res_rqts
    #print "======================"

def get_scheduled_jobs(resource_set): #available_suspended_res_itvs, now
    # TODO GanttJobsPrediction => GanttJobsPredictionS
    req = db.query(Job,\
                   GanttJobsPrediction.start_time,\
                   MoldableJobDescription.walltime,\
                   GanttJobsResource.resource_id)\
            .filter(MoldableJobDescription.index == 'CURRENT')\
            .filter(GanttJobsResource.moldable_job_id == GanttJobsPrediction.moldable_job_id)\
            .filter(MoldableJobDescription.id == GanttJobsPrediction.moldable_job_id)\
            .filter(Job.id == MoldableJobDescription.id)\
            .order_by(Job.start_time, Job.id)\
            .all()

    jobs = []
    prev_j_id = 0
    roids = []
    job_ugly = {} # ugly workaround for  UnboundLocalError: local variable 'job' referenced before assignment 
    #               witrh Python 3 use nonlocal keyword
    #(job, a, b, c) = req[0]
    if req != []:
        for x in req:
            (j, start_time, walltime, r_id) = x
            print x
            if j.id != prev_jid: 
                if prev_jid != 0:
                    job.res_set = unordered_ids2itvs(roids)
                    jobs.append(job)
                    roids = []
                    
                job = j
                job.start_time = start_time
                job.walltime = walltime
                job_ugly[1] = job 
                    
            roids.append(resource_set.rid_i2o[r_id])

        job = job_ugly[1]
        job.res_set = unordered_ids2itvs(roids)
        jobs.append(job)
    
    return jobs

def save_assigns(jobs, resource_set):
    #http://docs.sqlalchemy.org/en/rel_0_9/core/dml.html#sqlalchemy.sql.expression.Insert.values
    mld_id_start_time_s = []
    for j in jobs.itervalues():
        mld_id_start_time_s.append( (j.moldable_id, j.start_time) )
        riods = itvs2ids(j.res_set) 
        mld_id_rid_s = [(j.moldable_id, resource_set.rid_o2i[rid]) for rid in riods]
        mld_id_rid_s.append( (j.moldable_id, mld_id_rid_s) )

    GanttJobsPrediction.__table__.insert().values( mld_id_start_time_s )
    GanttJobsResource.__table__.insert().values( mld_id_rid_s )

    #"INSERT INTO  gantt_jobs_predictions  (moldable_job_id,start_time) VALUES "^
    #"INSERT INTO  gantt_jobs_resources (moldable_job_id,resource_id) VALUES "^

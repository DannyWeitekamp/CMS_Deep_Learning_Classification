import sys,os
import numpy as np
import json
import shlex
import subprocess

from time import time,sleep
import select
import importlib
from six import string_types

import CMS_Deep_Learning
from .archiving import KerasTrial, DataProcedure
from .batch import batchAssertArchived

MPI_INPUT_DEFAULTS = { "masters" : 1,
                       "workers" : 2,
                       "max_gpus" : 2,
                       "master_gpu" : False,
                       "synchronous" : False,
                       "master_optimizer" : "rmsprop",
                       #"worker_optimizer" : "rmsprop",
                       "sync_every" : 1,
                       "easgd" : False,
                       "elastic_force" : 0.9,
                       "elastic_lr" : 1.0,
                       "elastic_momentum" : 0.0,
                       "features_name":"X",
                       "labels_name":"Y"

}

class MPI_KerasTrial(KerasTrial):
    
    def __init__(self,*args, **kargs):
        custom_objects = None
        if("custom_objects" in kargs):
            custom_objects = kargs["custom_objects"]
            del kargs["custom_objects"]
        #print(custom_objects)
        if(custom_objects != None): 
            self.setCustomObjects(custom_objects)
        else:
            self.custom_objects = {}


        for key,value in MPI_INPUT_DEFAULTS.items():
            if(key in kargs):
                setattr(self, key, kargs[key])
            else:
                setattr(self, key, value)

        if not "max_gpus" in kargs:
            setattr(self, "max_gpus", self.masters + self.workers)

        #print(self.custom_objects)
        #raise ValueError()
        KerasTrial.__init__(self,*args,**kargs)

    def _remove_dict_defaults(self, d):
        del_keys = []
        for key in d:
            if(key in MPI_INPUT_DEFAULTS and MPI_INPUT_DEFAULTS[key] == d[key]):
                del_keys.append(key)
        for key in del_keys:
            del d[key]

        d = super(MPI_KerasTrial, self)._remove_dict_defaults(d)
        return d





    def setCustomObjects(self,custom_objects):
        self.custom_objects = {name:obj.__module__ if hasattr(obj, "__module__") else obj for name, obj in custom_objects.items()}
    
    # print("MOOPGS")

    def kill(self, p):
        print("Killing %r and related processes" % self.hash(),p.pid,os.getpgid(p.pid))
        p.kill()
        del p
        sys.exit()
    def execute(self, archiveTraining=True,
                archiveValidation=True,
                verbosity=1,
                # numProcesses=2
                ):
        # print(kargs)
        # if(not "isMPI_Instance" in kargs):
        if(not self.is_complete()):
            self.write()
            
            # comm = MPI.COMM_WORLD.Dup()
            # print("Not MPI_Instance")
            p = os.path.dirname( os.path.abspath(CMS_Deep_Learning.__file__))
            loc = p + "/storage/MPIKerasTrial_execute.py"
            print(self.archive_dir, self.hash())
            RunCommand = 'mpirun -np %s python %s %s %s --masters %s --max-gpus %s' % (self.workers + self.masters, loc, self.archive_dir, self.hash(), self.masters, self.max_gpus)
            print(RunCommand)

            args = shlex.split(RunCommand)
            env=os.environ
            new_env = {k: v for k, v in env.iteritems() if "MPI" not in k}
            
            p = subprocess.Popen("exec " + RunCommand,shell=True, env=new_env,stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                while True:
                    reads = [p.stdout.fileno(), p.stderr.fileno()]
                    ret = select.select(reads, [], [])
                    for fd in ret[0]:
                        if fd == p.stdout.fileno():
                            read = p.stdout.readline()
                            sys.stdout.write(read)
                        if fd == p.stderr.fileno():
                            read = p.stderr.readline()
                            sys.stderr.write(read)
                    if p.poll() != None:
                        break
            except :
                self.kill(p)
            # except Exception as e:
                # self.kill(p)
                
        else:
            print("Trial %r Already Complete" % self.hash())
        self._history_to_record(['val_acc'])
        history = self.get_history()
        if(history != None):self.to_record( {'elapse_time' : history.get('elapse_time', "??"),
                                             'last_epoch': history.get('last_epoch'),
                                             'start_time': history.get('start_time')
                                            }, replace=True)
        # dct =  {'num_train' : self.samples_per_epoch,
        #             'num_validation' : num_val,
        #             'elapse_time' : self.get_history()['elapse_time'],
        #             # 'fit_cycles' : len(train_procs)
        #             }
            # self.to_record( dct, replace=True)
        return
            
    def _execute_MPI(self,
                    comm=None,
                    # masters=1,
                    # easgd=False,
                    archiveTraining=True,
                    archiveValidation=True,
                    verbose=1):
        from mpi4py import MPI
        from mpi_learn.mpi.manager import MPIManager, get_device
        from mpi_learn.train.algo import Algo
        from mpi_learn.train.data import H5Data
        from mpi_learn.train.model import ModelFromJson

        #return prep_func
        #print(self.custom_objects)
        #print(custom_objects)
        #print(Lorentz, Slice)
        #raise ValueError()
        load_weights = True
        # synchronous = False
        # sync_every = 1
        # MPIoptimizer = "rmsprop"
        # batch_size = 100
        
        if(comm == None):
            comm = MPI.COMM_WORLD.Dup()



        # if(not isinstance(self.train_procedure,list)): self.train_procedure = [self.train_procedure]
        # if(not isinstance(self.val_procedure,list)): self.val_procedure = [self.val_procedure]
        if(not(isinstance(self.train_procedure,list))):
            raise ValueError("Trial attribute train_procedure: expected list of DataProcedures or paths but got type %r" % type(self.train_procedure))
        if(not(isinstance(self.val_procedure,list))):
            raise ValueError("Trial attribute val_procedure: expected list of DataProcedures or paths but got type %r" % type(self.val_procedure))

        train = [DataProcedure.from_json(self.archive_dir,x) if isinstance(x,DataProcedure) else str(x) for x in self.train_procedure]
        val = [DataProcedure.from_json(self.archive_dir,x) if isinstance(x,DataProcedure) else str(x) for x in self.val_procedure]

        # if(not isinstance(train, list) or not False in [isinstance(x,DataProcedure) or isinstance(x,string_types) for x in train]):
        #     raise ValueError("Train procedure must be list of DataProcedures")
        # if(not isinstance(val, list) or not False in [isinstance(x, DataProcedure) or isinstance(x, string_types) for x in val]):
        #     raise ValueError("Validation procedure must be list of DataProcedures")
        batchAssertArchived(train)
        batchAssertArchived(val)
        def assertStr(x):
            if(isinstance(x,DataProcedure)):
                return dp.get_path() + "archive.h5"
            elif(os.path.isfile(x)):
                return x  
            else:
                raise IOError("Cannot find %r" % x)
                
        train_list = [assertStr(x) for x in train]
        val_list = [assertStr(x) for dp in val]
        # print("Train List:", train_list)
        # print("Val List:", val_list)

        # There is an issue when multiple processes import Keras simultaneously --
        # the file .keras/keras.json is sometimes not read correctly.  
        # as a workaround, just try several times to import keras.
        # Note: importing keras imports theano -- 
        # impossible to change GPU choice after this.
        for try_num in range(10):
            try:
                from keras.models import model_from_json
                import keras.callbacks as cbks
                break
            except ValueError:
                print "Unable to import keras. Trying again: %d" % try_num
                sleep(0.1)


        custom_objects = {}
        for name, module in self.custom_objects.items():
            try:
                #my_module = importlib.import_module('os.path')
                custom_objects[name] = getattr(importlib.import_module(module), name)
                #exec("from " + module +  " import " + name)
            except:
                raise ValueError("Custom Object %r does not exist in %r. \
                    For best results Custom Objects should be importable and not locally defined." % (str(name), str(module)))

        # We initialize the Data object with the training data list
        # so that we can use it to count the number of training examples

        data = H5Data(batch_size=self.batch_size, 
                features_name=self.features_name, labels_name=self.labels_name)
        data.set_file_names(train_list)
        num_train = data.count_data()
        


        # if comm.Get_rank() == 0:
        validate_every = num_train/self.batch_size
       
        

        if self.easgd:
            # raise NotImplementedError("Not implemented")
            algo = Algo(None, loss=self.loss, validate_every=validate_every,
                    mode='easgd', elastic_lr=1.0, sync_every=self.sync_every,
                    worker_optimizer='sgd',
                    elastic_force=0.9/(comm.Get_size()-1)) 
        else:
            algo = Algo(self.master_optimizer, loss=self.loss, validate_every=validate_every,
                    sync_every=self.sync_every, worker_optimizer=self.optimizer) 

        #model = self.compile(custom_objects=custom_objects)
        #model_arch = model.to_json()
        #print(self.get_path()+"trial.json")
        model_builder = ModelFromJson( comm,json_str=self.model,custom_objects=custom_objects )

        callbacks = self._generateCallbacks(verbose=verbose)

        # Creating the MPIManager object causes all needed worker and master nodes to be created
        manager = MPIManager(comm=comm, data=data, num_epochs=self.epochs if hasattr(self,'epochs') else self.nb_epoch,
                             algo=algo, model_builder=model_builder,
                             train_list=train_list, val_list=val_list, num_masters=self.masters,
                             synchronous=self.synchronous, callbacks=callbacks, custom_objects=custom_objects)


        # Process 0 defines the model and propagates it to the workers.
        if comm.Get_rank() == 0:
            record = self.read_record()
            if(not "num_train" in record):
                self.to_record({"num_train": num_train})
            if(not "num_val" in record):
                val_data = H5Data( val_list, batch_size=self.batch_size,
                features_name=self.features_name, labels_name=self.labels_name)
                self.to_record({"num_val": val_data.count_data()})

            print(custom_objects)
            
            
            print algo
            #weights = model.get_weights()

            #manager.process.set_model_info( model_arch, algo, weights )
            t_0 = time()
            histories = manager.process.train() 
            delta_t = time() - t_0
            manager.free_comms()
            print "Training finished in %.3f seconds" % delta_t
            print(histories)

            
            

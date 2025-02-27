'''DEPRICATED
	just a quick script to translate from an old archiving format
'''
import os
import sys

if __package__ is None:
    sys.path.append(os.path.realpath("../"))
from CMS_Deep_Learning.storage.archiving import *

def forwardComp(archive_dir):
	trial_record = KerasTrial.read_record(archive_dir)
	data_record = DataProcedure.read_record(archive_dir)
	for key, value in trial_record.items():
		trial = KerasTrial.find(archive_dir, key)
		path = trial.get_path()
		print(path)
		write_json_obj(value, path,'record.json')
	for key, value in data_record.items():
		dp = DataProcedure.find(archive_dir, key)
		path = dp.get_path()
		print(path)
		write_json_obj(value, path,'record.json')

if __name__ == "__main__":
   forwardComp(sys.argv[1])

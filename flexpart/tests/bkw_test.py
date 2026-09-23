import netCDF4 as nc
import numpy as np
import os
import re

return_flag = False

resolution=0.01

compare = False
path1="./output_bkw/"
patheta="./output_bkw_eta/"
# Comparing to previous version, if it exists
if (os.path.isfile("./bkw_master.txt")):
  compare = True
  fr = open("./bkw_master.txt", "r")

output_name = 'bkw_test.txt'
with open(output_name, 'a') as f:

  ndata = nc.Dataset(path1+"grid_drydep_20090101030000.nc", 'r')

  print("Checking gridded output...")
  #Concentrations
  temp=np.abs(ndata['spec001_mr'][:,:,1,:,:,:])
  mn_c=np.mean(temp)
  mx_c=np.max(temp)
  f.write(" Dry:\t\tmean abs: %2.8e\tmax abs: %2.8e\n" %(mn_c,mx_c))
  if compare:
    tmp=fr.readline()
    tmp2=tmp.split()
    mn_prev=float(tmp2[3])
    mx_prev=float(tmp2[6])
    diff_pr=np.abs(mn_c-mn_prev)/np.abs(mn_c)*100.
    if (diff_pr>resolution):
      print("WARNING: DRY deposition gives a different mean value compared to the previous version.")
      print(diff_pr, "percent")
      return_flag = True
    diff_pr=np.abs(mx_c-mx_prev)/np.abs(mx_c)*100.
    if (diff_pr>resolution):
      print("WARNING: DRY deposition gives a different max value compared to the previous version.")
      print(diff_pr, "percent")
      return_flag = True
    #f.write(tmp)
    #f.write("\n")
  ndata.close()

  ndata = nc.Dataset(patheta+"grid_drydep_20090101030000.nc", 'r')
    
  print("Checking gridded output...")
  #Concentrations
  temp=np.abs(ndata['spec001_mr'][:,:,1,:,:,:])
  mn_c=np.mean(temp)
  mx_c=np.max(temp)
  f.write(" Dry ETA:\tmean abs: %2.8e\tmax abs: %2.8e\n" %(mn_c,mx_c))
  if compare:
    tmp=fr.readline()
    tmp2=tmp.split()
    mn_prev=float(tmp2[4])
    mx_prev=float(tmp2[7])
    diff_pr=np.abs(mn_c-mn_prev)/np.abs(mn_c)*100.
    if (diff_pr>resolution):
      print("WARNING: DRY ETA deposition gives a different mean value compared to the previous version.")
      print(diff_pr, "percent")
      return_flag = True
    diff_pr=np.abs(mx_c-mx_prev)/np.abs(mx_c)*100.
    if (np.abs(mx_c-mx_prev)>(np.abs(mx_c)/resolution)):
      print("WARNING: DRY ETA deposition gives a different max value compared to the previous version.")
      print(diff_pr, "percent")
      return_flag = True
    #f.write(tmp)
    #f.write("\n")
  ndata.close()

  ndata = nc.Dataset(path1+"grid_wetdep_20090101030000.nc", 'r')
  
  print("Checking gridded output...")
  #Concentrations
  temp=np.abs(ndata['spec001_mr'][:,:,1,:,:,:])
  mn_c=np.mean(temp)
  mx_c=np.max(temp)
  f.write(" Wet:\t\tmean abs: %2.8e\tmax abs: %2.8e\n" %(mn_c,mx_c))
  if compare:
    tmp=fr.readline()
    tmp2=tmp.split()
    mn_prev=float(tmp2[3])
    mx_prev=float(tmp2[6])
    diff_pr=np.abs(mn_c-mn_prev)/np.abs(mn_c)*100.
    if (diff_pr>resolution):
      print("WARNING: WET deposition gives a different mean value compared to the previous version.")
      print(diff_pr, "percent")
      return_flag = True
    diff_pr=np.abs(mx_c-mx_prev)/np.abs(mx_c)*100.
    if (np.abs(mx_c-mx_prev)>(np.abs(mx_c)/resolution)):
      print("WARNING: WET deposition gives a different max value compared to the previous version.")
      print(diff_pr, "percent")
      return_flag = True
    #f.write(tmp)
    #f.write("\n")
  ndata.close()

  ndata = nc.Dataset(patheta+"grid_wetdep_20090101030000.nc", 'r')
  
  print("Checking gridded output...")
  #Concentrations
  temp=np.abs(ndata['spec001_mr'][:,:,1,:,:,:])
  mn_c=np.mean(temp)
  mx_c=np.max(temp)
  f.write(" Wet ETA:\tmean abs: %2.8e\tmax abs: %2.8e\n" %(mn_c,mx_c))
  if compare:
    tmp=fr.readline()
    tmp2=tmp.split()
    mn_prev=float(tmp2[4])
    mx_prev=float(tmp2[7])
    diff_pr=np.abs(mn_c-mn_prev)/np.abs(mn_c)*100.
    if (np.abs(mn_c-mn_prev)>(np.abs(mn_c)/resolution)): 
      print("WARNING: WET ETA deposition gives a different mean value compared to the previous version.")
      print(diff_pr, "percent")
      return_flag = True
    diff_pr=np.abs(mx_c-mx_prev)/np.abs(mx_c)*100.
    if (np.abs(mx_c-mx_prev)>(np.abs(mx_c)/resolution)):
      print("WARNING: WET ETA deposition gives a different max value compared to the previous version.")
      print(diff_pr, "percent")
      return_flag = True
    #f.write(tmp)
    #f.write("\n")
  ndata.close()

if (return_flag):
  raise ValueError('Old and New version deviate')
elif (compare):
  print("Output from previous version is not significantly different from this version.")

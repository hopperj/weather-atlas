import netCDF4 as nc
import numpy as np
import os

path1="./output_omp1/"
path32="./output_omp32/"

path1eta="./output_omp1_eta/"
path32eta="./output_omp32_eta/"

fdate="20090101000000"

ndata_1 = nc.Dataset(path1+"partoutput_"+fdate+"_init.nc", 'r')
ndata_32 = nc.Dataset(path32+"partoutput_"+fdate+"_init.nc", 'r')

dvars = list(ndata_1.variables)
for idvars in dvars:
  temp = ndata_1[idvars][:]-ndata_32[idvars][:]
  mn=np.mean(np.abs(temp))
  mx=np.max(np.abs(temp))
  mean1=(np.mean(np.abs(ndata_1[idvars])))
  print(idvars,": ","mean difference:",mn," max abs difference:",mx, "abs mean: ", mean1)
  if (mn>(mean1/1.e8)):
    print('Mean difference exceeds allowed value of ',mean1/1.e8)
    #raise ValueError('Mean allowed difference exceeded.')
ndata_1.close()
ndata_32.close()

ndata_1 = nc.Dataset(path1+"grid_conc_"+fdate+".nc", 'r')
ndata_32 = nc.Dataset(path32+"grid_conc_"+fdate+".nc", 'r')

print("Checking gridded output...")
#Concentrations
temp=ndata_1['spec001_mr'][:]-ndata_32['spec001_mr'][:]
mn_c=np.mean(temp)
mx_c=np.max(temp)
mn_c1=np.mean(np.abs(ndata_1['spec001_mr'][:]))
print("Concentrations: mean difference",mn_c," max abs difference:",mx_c, "abs mean: ",mn_c1)
if (mn_c>(mn_c1/1.e8)):
  print('Gridded concentration output: mean difference exceeds allowed value of ',mn_c1/1.e8)
  #raise ValueError('Gridded concentration output deviates between serial and OMP version')

#Wet deposition
temp=ndata_1['WD_spec001'][:]-ndata_32['WD_spec001'][:]
mn_c=np.mean(temp)
mx_c=np.max(temp)
mn_c1=np.mean(np.abs(ndata_1['spec001_mr'][:]))
print("WET deposition: mean difference",mn_c," max abs difference:",mx_c, "abs mean: ",mn_c1)
if (mn_c>(mn_c1/1.e8)):
  print('Gridded WET deposition output: mean difference exceeds allowed value of ',mn_c1/1.e8)
  raise ValueError('Gridded WET deposition output deviates between serial and OMP version')

#Dry deposition
temp=ndata_1['DD_spec001'][:]-ndata_32['DD_spec001'][:]
mn_c=np.mean(temp)
mx_c=np.max(temp)
mn_c1=np.mean(np.abs(ndata_1['spec001_mr'][:]))
print("DRY deposition: mean difference",mn_c," max abs difference:",mx_c, "abs mean: ",mn_c1)
if (mn_c>(mn_c1/1.e8)):
  print('Gridded DRY deposition output: mean difference exceeds allowed value of ',mn_c1/1.e8)
  raise ValueError('Gridded DRY deposition output deviates between serial and OMP version')

ndata_1.close()
ndata_32.close()

ndata_1 = nc.Dataset(path1eta+"partoutput_"+fdate+"_init.nc", 'r')
ndata_32 = nc.Dataset(path32eta+"partoutput_"+fdate+"_init.nc", 'r')

dvars = list(ndata_1.variables)
for idvars in dvars:
  temp = ndata_1[idvars][:]-ndata_32[idvars][:]
  mn=np.mean(np.abs(temp))
  mx=np.max(np.abs(temp))
  mean1=(np.mean(np.abs(ndata_1[idvars])))
  print(idvars,"ETA: ","mean difference:",mn," max abs difference:",mx, "abs mean: ", mean1)
  if (mn>(mean1/1.e8)):
    print('Mean ETA difference exceeds allowed value of ',mean1/1.e8)
    #raise ValueError('Mean ETA allowed difference exceeded.')
ndata_1.close()
ndata_32.close()

ndata_1 = nc.Dataset(path1eta+"grid_conc_"+fdate+".nc", 'r')
ndata_32 = nc.Dataset(path32eta+"grid_conc_"+fdate+".nc", 'r')

print("Checking gridded output...")
#Concentrations
temp=ndata_1['spec001_mr'][:]-ndata_32['spec001_mr'][:]
mn_c=np.mean(temp)
mx_c=np.max(temp)
mn_c1=np.mean(np.abs(ndata_1['spec001_mr'][:]))
print("Concentrations ETA: mean difference",mn_c," max abs difference:",mx_c, "abs mean: ",mn_c1)
if (mn_c>(mn_c1/1.e8)):
  print('Gridded ETA concentration output: mean difference exceeds allowed value of ',mn_c1/1.e8)
  #raise ValueError('Gridded ETA concentration output deviates between serial and OMP version')

#Wet deposition
temp=ndata_1['WD_spec001'][:]-ndata_32['WD_spec001'][:]
mn_c=np.mean(temp)
mx_c=np.max(temp)
mn_c1=np.mean(np.abs(ndata_1['spec001_mr'][:]))
print("WET deposition ETA: mean difference",mn_c," max abs difference:",mx_c, "abs mean: ",mn_c1)
if (mn_c>(mn_c1/1.e8)):
  print('Gridded WET ETA deposition output: mean difference exceeds allowed value of ',mn_c1/1.e8)
  raise ValueError('Gridded WET ETA deposition output deviates between serial and OMP version')

#Dry deposition
temp=ndata_1['DD_spec001'][:]-ndata_32['DD_spec001'][:]
mn_c=np.mean(temp)
mx_c=np.max(temp)
mn_c1=np.mean(np.abs(ndata_1['spec001_mr'][:]))
print("DRY deposition ETA: mean difference",mn_c," max abs difference:",mx_c, "abs mean: ",mn_c1)
if (mn_c>(mn_c1/1.e8)):
  print('Gridded DRY ETA deposition output: mean difference exceeds allowed value of ',mn_c1/1.e8)
  raise ValueError('Gridded DRY ETA deposition output deviates between serial and OMP version')

ndata_1.close()
ndata_32.close()
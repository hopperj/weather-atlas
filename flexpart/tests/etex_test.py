#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from netCDF4 import Dataset, chartostring
import numpy as np
import pandas as pd
from scipy import stats


class Grid:
  def __init__(
    self,
    path_to_directory="/home/lucie/ETEX_PS_2000/output/",
    fname="grid_conc_19941023160000.nc",
    varname="spec001_mr",
  ):
    self.path = path_to_directory
    self.fname = fname
    self.varname = varname
    self._read_file()

  def _read_file(self):
    tempfile = self.path + "/" + self.fname
    self._data = Dataset(tempfile, "r", format="NETCDF4")
    print("netCDF4 file opened.")
    if "receptorname" in self._data.variables:
      self.receptornames = np.char.strip(
        chartostring(self._data["receptorname"][:])
      )

  def close(self):
    self._data.close()
    print("netCDF4 file closed.")

  @property
  def recordlen(self):
    if "AIRTRACER" == self.varname:
      return np.unique(self._data["time"][:])
    else:
      return self._data["time"][:]
      

  @property
  def dataset(self):
    return self._data[self.varname]

  @property
  def longitude(self):
    if "longitude" in self._data.variables:
      return np.array(self._data["longitude"][:])
    elif "lon" in self._data.variables:
      return np.array(self._data["lon"][:])
    else:
      raise ValueError("Longitude variable not found in the dataset.")

  @property
  def latitude(self):
    if "latitude" in self._data.variables:
      return np.array(self._data["latitude"][:])
    elif "lat" in self._data.variables:
      return np.array(self._data["lat"][:])
    else:
      raise ValueError("Latitude variable not found in the dataset.")

  @property
  def height(self):
    if "height" in self._data.variables:
      return np.array(self._data["height"][:])
    elif "lev" in self._data.variables:
      return np.array(self._data["lev"][:])
    else:
      raise ValueError("Height variable not found in the dataset.")

  def concentration_rec(self, station):
    if "AIRTRACER" == self.varname:
      return np.array(self.dataset[self.receptornames == station])
    else:
      raise ValueError("Invalid variable name for concentration_rec.")

  def concentration(self, lat, lon, height=None):
    ilon = np.abs(self.longitude - lon).argmin()
    ilat = np.abs(self.latitude - lat).argmin()
    if height is None:
      return np.sum(np.array(self.dataset[0, 0,:, 0:1, ilat, ilon]), axis=1)
    else:
      iheight = np.abs(self.height - height).argmin()
      dh1 = np.abs(self.height[iheight] - height) / (
        self.height[iheight + 1] - self.height[iheight]
      )
      return (1.0 - dh1) * (
        np.sum(self.dataset[:, iheight, ilat, ilon])
        + dh1 * np.array(self.dataset[:, iheight + 1, ilat, ilon])
      )


class Etex:
  def __init__(
    self,
    path_to_directory="/home/lucie/ETEX_PS_2000/Statistik_ASt/",
    fname="pmch2.dat",
    locname="stationlist.950130",
  ):
    self.path = path_to_directory
    self.fname = fname
    self.locname = locname

    self._df = pd.read_csv(self.path + "/" + self.fname, delim_whitespace=True)
    self._loc = pd.read_csv(self.path + "/" + self.locname, sep=",")

  @property
  def df(self):
    return self._df

  @property
  def loc(self):
    return self._loc[["cc", " Lat", " Long", " Alt"]]

  @property
  def stations(self):
    return self.loc["cc"].to_numpy()

  def location(self, station):
    index = np.where(self.loc["cc"] == station)[0][0]
    loctemp = self.loc.loc[[index]].to_numpy()[0, 1:].astype(float)
    d0 = int(loctemp[0]) + (loctemp[0] - int(loctemp[0])) / 0.6
    d1 = int(loctemp[1]) + (loctemp[1] - int(loctemp[1])) / 0.6
    return np.array([d0, d1, loctemp[2]])  # , loctemp

  def concentration(self, station):
    index = np.where(self.df["station"] == station)[0][0]
    return self.df.loc[[index]].to_numpy()[0, 1:].astype(float)


def compute_etex_concentrations(grid, etex):
  lengte = np.min([len(etex.concentration(etex.stations[0])), len(grid.recordlen)])
  econc = np.zeros((len(etex.stations), lengte))
  # gconc=np.zeros((len(etex.stations),lengte))
  rconc = np.zeros((len(etex.stations), lengte))  # len(grid.data)))

  i = 0
  for station in etex.stations:
    econc_tmp = etex.concentration(station)[: len(econc[0])]
    if grid.varname == "AIRTRACER":
      rconc_tmp = grid.concentration_rec(station)
      if rconc_tmp.size == 0:
        continue
    else:
      ilon, ilat, _ = etex.location(station)
      rconc_tmp = grid.concentration(ilon, ilat)

    rconc_tmp[rconc_tmp < 0.01] = 0.0
    rconc[i, :] = rconc_tmp
    ww = np.where(econc_tmp < 0)[0]
    econc_tmp[(econc_tmp < 0.01)] = 0.0
    econc_tmp[ww] = -1
    econc[i, :] = econc_tmp
    # loc=etex.location(station)
    # gconc_tmp=grid.concentration(loc[0],loc[1],1)[:len(etex.stations)]
    # gconc_tmp[(gconc_tmp<0.01) & (gconc_tmp>=0.005)]=0.01
    # gconc_tmp[(gconc_tmp<0.01)]=0.0

    # gconc[i,:]=gconc_tmp
    i += 1

  return econc, rconc


def compute_error_measures(
  econc, gconc, output_name="./etex_test.txt", print_to_screen=False
):
  gconcf = gconc.flatten()
  econcf = econc.flatten()
  # rconcf=rconc.flatten()
  ww = np.where(econcf >= 0)[0]
  # econcf[ww]=econcf[ww]+(np.random.rand(len(ww))-0.5)*0.1
  ww2 = np.where(econcf > 0)[0]
  nmse_1 = (
    np.sum((gconcf[ww] - econcf[ww]) ** 2)
    / (np.mean(gconcf[ww]) * np.mean(econcf[ww]))
    / (len(ww))
  )
  # nmser_1 = np.sum((rconcf[ww]-econcf[ww])**2)/(np.mean(rconcf[ww])*np.mean(econcf[ww]))/(len(ww))
  # nmserg_1 = np.sum((rconcf[ww]-gconcf[ww])**2)/(np.mean(rconcf[ww])*np.mean(gconcf[ww]))/(len(ww))

  b = 1.0 / len(econcf[ww]) * np.sum(gconcf[ww] - econcf[ww])
  fb = 2 * b / (np.mean(gconcf[ww]) + np.mean(econcf[ww]))

  fms = (
    100
    * len(np.where((gconcf > 0.1) & (econcf > 0.1))[0])
    / len(np.where(gconcf + econcf > 0.1)[0])
  )

  ps = stats.pearsonr(econcf[ww], gconcf[ww])

  sm = stats.spearmanr(econcf[ww], gconcf[ww])

  fa2 = len(np.where(econcf[ww] * 2 >= gconcf[ww])[0]) / len(ww)
  fa5 = len(np.where(econcf[ww] * 5 >= gconcf[ww])[0]) / len(ww)
  foex = 100 * (
    len(np.where(gconcf[ww2] > econcf[ww2])[0])
    / len(ww2 - len(np.where(gconcf[ww2] == econcf[ww2])[0]))
    - 0.5
  )
  infos = """fb: {:.6f}
nmse: {:.6f}
fms: {:.6f}
ps: {:.6f}
sm: {:.6f}
fa2: {:.6f}
fa5: {:.6f}
foex: {:.6f}
N: {:d}
N>0: {:d}""".format(fb, nmse_1, fms, ps[0], sm[0], fa2, fa5, foex, len(ww), len(ww2))
  if print_to_screen:
    print(infos)
  else:
    with open(output_name, "a") as f:
      f.write(infos)


if __name__ == "__main__":
  if "DEBUG" in os.environ:
    print("DEBUG mode is on.")
  
  grid = Grid(path_to_directory="./output_etex/", fname="grid_conc_19941023160000.nc")
  etex = Etex(path_to_directory="./default_etex/")
  econc, gconc = compute_etex_concentrations(grid, etex)
  compute_error_measures(econc, gconc, "./etex_test.txt", print_to_screen="DEBUG" in os.environ)
  
  if "DEBUG" in os.environ:
    # grid = Grid(path_to_directory="./output_etex/", fname="grid_conc_19941023160000.nc")
    grid = Grid(path_to_directory="./output_etex/", fname="receptor_conc.nc", varname="AIRTRACER")
    # very wird results?
    etex = Etex(path_to_directory="./default_etex/")
    econc, gconc = compute_etex_concentrations(grid, etex)
    compute_error_measures(econc, gconc, "./etex_test.txt", print_to_screen="DEBUG" in os.environ)
  

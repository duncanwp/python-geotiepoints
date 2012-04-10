#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2010-2012.

# Author(s):
 
#   Adam Dybbroe <adam.dybbroe@smhise>
#   Martin Raspaud <martin.raspaud@smhi.se>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Interpolation of geographical tiepoints.
"""

import numpy as np
from numpy import arccos, sign, rad2deg, sqrt, arcsin
from pyresample import geometry
from scipy.interpolate import RectBivariateSpline


EARTH_RADIUS = 6371000.0


def modis5kmto1km(lons5km, lats5km):
    """Getting 1km geolocation for modis from 5km tiepoints.
    """
    cols5km = np.arange(2, 1354, 5)
    cols1km = np.arange(1354)
    lines = lons5km.shape[0] * 5
    rows5km = np.arange(2, lines, 5)
    rows1km = np.arange(lines)

    along_track_order = 1
    cross_track_order = 3
    
    satint = SatelliteInterpolator((lons5km, lats5km),
                                   (rows5km, cols5km),
                                   (rows1km, cols1km),
                                   along_track_order,
                                   cross_track_order,
                                   10)
    satint.fill_borders("y", "x")
    lons1km, lats1km = satint.interpolate()
    return lons1km, lats1km

def modis1kmto500m(lons1km, lats1km):
    """Getting 500m geolocation for modis from 1km tiepoints.
    """
    cols1km = np.arange(0, 2708, 2)
    cols500m = np.arange(2708)
    lines = lons1km.shape[0] * 2
    rows1km = np.arange(0.5, lines, 2)
    rows500m = np.arange(lines)

    along_track_order = 1
    cross_track_order = 3
    
    satint = SatelliteInterpolator((lons1km, lats1km),
                                   (rows1km, cols1km),
                                   (rows500m, cols500m),
                                   along_track_order,
                                   cross_track_order,
                                   20)
    satint.fill_borders("y", "x")
    lons500m, lats500m = satint.interpolate()
    return lons500m, lats500m

def modis1kmto250m(lons1km, lats1km):
    """Getting 250m geolocation for modis from 1km tiepoints.
    """
    cols1km = np.arange(0, 5416, 4)
    cols250m = np.arange(5416)
    lines = lons1km.shape[0] * 4
    rows1km = np.arange(1.5, lines, 4)
    rows250m = np.arange(lines)

    along_track_order = 1
    cross_track_order = 3
    
    satint = SatelliteInterpolator((lons1km, lats1km),
                                   (rows1km, cols1km),
                                   (rows250m, cols250m),
                                   along_track_order,
                                   cross_track_order,
                                   40)
    satint.fill_borders("y", "x")
    lons250m, lats250m = satint.interpolate()
    return lons250m, lats250m


# TODO: extrapolate on a sphere ?
def _linear_extrapolate(pos, data, xev):
    """

    >>> import numpy as np
    >>> pos = np.array([1, 2])
    >>> data = np.arange(10).reshape((2, 5), order="F")
    >>> xev = 5
    >>> _linear_extrapolate(pos, data, xev)
    array([  4.,   6.,   8.,  10.,  12.])
    >>> xev = 0
    >>> _linear_extrapolate(pos, data, xev)
    array([-1.,  1.,  3.,  5.,  7.])
    """
    if len(data) != 2 or len(pos) != 2:
        raise ValueError("len(pos) and the number of lines of data"
                         " must be 2.")

    return data[1] + ((xev - pos[1]) / (1.0 * (pos[0] - pos[1])) *
                      (data[0] - data[1]))

class SatelliteInterpolator(object):
    """
    Handles interpolation of geolocation data from a grid of tie points.  It is
    preferable to have tie-points out till the edges if the tiepoint grid, but
    a method is provided to extrapolate linearly the tiepoints to the borders
    of the grid.

    Uses numpy, scipy, and pyresample

    The constructor takes in the tiepointed lon/lat data as *lon_lat_data*, the
    *tiepoint_grid* and the desired *final_grid*. As optional arguments, one
    can provide *kx* and *ky* as interpolation orders (in x and y directions
    respectively), and the *chunksize* if the data has to be handled by pieces
    along the y axis (this affects how the extrapolator behaves). If
    *chunksize* is set, don't forget to adjust the interpolation orders
    accordingly: the interpolation is indeed done globaly (not chunkwise).
    """

    def __init__(self, lon_lat_data, tiepoint_grid, final_grid,
                 kx=1, ky=1, chunk_size=0):
        self.row_indices = tiepoint_grid[0]
        self.col_indices = tiepoint_grid[1]
        self.hrow_indices = final_grid[0]
        self.hcol_indices = final_grid[1]
        self.chunk_size = chunk_size
        self.lon_tiepoint = None
        self.lat_tiepoint = None
        self.set_tiepoints(lon_lat_data[0], lon_lat_data[1])
        self.longitude = None
        self.latitude = None
        swath = geometry.BaseDefinition(self.lon_tiepoint,
                                        self.lat_tiepoint)
        xyz = swath.get_cartesian_coords()
        self.x__ = xyz[:, :, 0]
        self.y__ = xyz[:, :, 1]
        self.z__ = xyz[:, :, 2]

        self.newx = None
        self.newy = None
        self.newz = None

        self.kx, self.ky = kx, ky
        
    def set_tiepoints(self, lon, lat):
        """Defines the lon,lat tie points.
        """
        self.lon_tiepoint = lon
        self.lat_tiepoint = lat

    def fill_borders(self, *args):
        """Extrapolate tiepoint lons and lats to fill in the border of the
        chunks.

        >>> import numpy as np
        >>> lons = np.arange(20).reshape((4, 5), order="F")
        >>> lats = np.arange(20).reshape((4, 5), order="C")
        >>> lines = np.array([2, 7, 12, 17])
        >>> cols = np.array([2, 7, 12, 17, 22])
        >>> hlines = np.arange(20)
        >>> hcols = np.arange(24)
        >>> satint = SatelliteInterpolator((lons, lats), (lines, cols), (hlines, hcols), chunk_size=10)
        >>> satint.fill_borders('x', 'y')
        >>> satint.x__
        array([[ 6384905.78040055,  6381081.08333225,  6371519.34066148,
                 6328950.00792935,  6253610.69157758,  6145946.19489936,
                 6124413.29556372],
               [ 6377591.95940176,  6370997.        ,  6354509.6014956 ,
                 6305151.62592155,  6223234.99818839,  6109277.14889072,
                 6086485.57903118],
               [ 6359307.40690478,  6345786.79166939,  6311985.2535809 ,
                 6245655.67090206,  6147295.76471541,  6017604.5338691 ,
                 5991666.28769983],
               [ 6351993.58590599,  6335702.70833714,  6294975.51441502,
                 6221857.28889426,  6116920.07132621,  5980935.48786045,
                 5953738.5711673 ],
               [ 6338032.26190294,  6320348.4990906 ,  6276139.09205974,
                 6199670.56624433,  6091551.90273768,  5952590.38414781,
                 5924798.08042984],
               [ 6290665.5946295 ,  6270385.16249031,  6219684.08214232,
                 6137100.75832981,  6023313.2794414 ,  5879194.72399075,
                 5850371.01290062],
               [ 6172248.92644589,  6145476.82098957,  6078546.55734877,
                 5980676.23854351,  5852716.72120069,  5695705.57359808,
                 5664303.34407756],
               [ 6124882.25917245,  6095513.48438928,  6022091.54743135,
                 5918106.430629  ,  5784478.09790441,  5622309.91344102,
                 5589876.27654834]])
        >>> satint.row_indices
        array([ 0,  2,  7,  9, 10, 12, 17, 19])
        >>> satint.col_indices
        array([ 0,  2,  7, 12, 17, 22, 23])
        """
        to_run = []
        cases = {"y": self._fill_row_borders,
                 "x": self._fill_col_borders}
        for dim in args:
            try:
                to_run.append(cases[dim])
            except KeyError:
                raise NameError("Unrecognized dimension: "+str(dim))

        for fun in to_run:
            fun()


    def _extrapolate_cols(self, data):
        """Extrapolate the column of data, to get the first and last together
        with the data.

        >>> import numpy as np
        >>> lons = np.arange(10).reshape((2, 5), order="F")
        >>> lats = np.arange(10).reshape((2, 5), order="C")
        >>> lines = np.array([2, 7])
        >>> cols = np.array([2, 7, 12, 17, 22])
        >>> hlines = np.arange(10)
        >>> hcols = np.arange(24)
        >>> satint = SatelliteInterpolator((lons, lats), (lines, cols), (hlines, hcols))
        >>> satint._extrapolate_cols(satint.x__)
        array([[ 6372937.31273379,  6370997.        ,  6366146.21816553,
                 6351605.98629588,  6327412.61244969,  6293626.50067273,
                 6286869.27831734],
               [ 6353136.46335726,  6345786.79166939,  6327412.61244969,
                 6299445.69529922,  6261968.60390423,  6215087.60607344,
                 6205711.40650728]])
        """

        pos = self.col_indices[:2]
        first_column = _linear_extrapolate(pos,
                                           (data[:, 0], data[:, 1]),
                                           self.hcol_indices[0])
        pos = self.col_indices[-2:]
        last_column = _linear_extrapolate(pos,
                                          (data[:, -2], data[:, -1]),
                                          self.hcol_indices[-1])

        return np.hstack((np.expand_dims(first_column, 1),
                          data,
                          np.expand_dims(last_column, 1))) 

    def _fill_col_borders(self):
        """Add the first and last column to the data by extrapolation.

        >>> import numpy as np
        >>> lons = np.arange(10).reshape((2, 5), order="F")
        >>> lats = np.arange(10).reshape((2, 5), order="C")
        >>> lines = np.array([2, 7])
        >>> cols = np.array([2, 7, 12, 17, 22])
        >>> hlines = np.arange(10)
        >>> hcols = np.arange(24)
        >>> satint = SatelliteInterpolator((lons, lats), (lines, cols), (hlines, hcols))
        >>> satint._fill_col_borders()
        >>> satint.x__
        array([[ 6372937.31273379,  6370997.        ,  6366146.21816553,
                 6351605.98629588,  6327412.61244969,  6293626.50067273,
                 6286869.27831734],
               [ 6353136.46335726,  6345786.79166939,  6327412.61244969,
                 6299445.69529922,  6261968.60390423,  6215087.60607344,
                 6205711.40650728]])
        >>> satint.col_indices
        array([ 0,  2,  7, 12, 17, 22, 23])
        """

        self.x__ = self._extrapolate_cols(self.x__)
        self.y__ = self._extrapolate_cols(self.y__)
        self.z__ = self._extrapolate_cols(self.z__)
  
        self.col_indices = np.concatenate((np.array([self.hcol_indices[0]]),
                                           self.col_indices,
                                           np.array([self.hcol_indices[-1]])))

    def _extrapolate_rows(self, data):
        """Extrapolate the rows of data, to get the first and last together
        with the data.

        >>> import numpy as np
        >>> lons = np.arange(10).reshape((2, 5), order="F")
        >>> lats = np.arange(10).reshape((2, 5), order="C")
        >>> lines = np.array([2, 7])
        >>> cols = np.array([2, 7, 12, 17, 22])
        >>> hlines = np.arange(10)
        >>> hcols = np.arange(24)
        >>> satint = SatelliteInterpolator((lons, lats), (lines, cols), (hlines, hcols))
        >>> satint._extrapolate_rows(satint.x__)
        array([[ 6381081.08333225,  6381639.66045187,  6372470.10269454,
                 6353590.21586788,  6325042.05851245],
               [ 6370997.        ,  6366146.21816553,  6351605.98629588,
                 6327412.61244969,  6293626.50067273],
               [ 6345786.79166939,  6327412.61244969,  6299445.69529922,
                 6261968.60390423,  6215087.60607344],
               [ 6335702.70833714,  6311919.17016336,  6278581.57890056,
                 6235791.00048604,  6183672.04823372]])
        """

        pos = self.row_indices[:2]
        first_row = _linear_extrapolate(pos,
                                        (data[0, :], data[1, :]),
                                        self.hrow_indices[0])
        pos = self.row_indices[-2:]
        last_row = _linear_extrapolate(pos,
                                       (data[-2, :], data[-1, :]),
                                       self.hrow_indices[-1])

        return np.vstack((np.expand_dims(first_row, 0),
                          data,
                          np.expand_dims(last_row, 0))) 

    def _fill_row_borders(self):
        """Add the first and last rows to the data by extrapolation.

        >>> import numpy as np
        >>> lons = np.arange(20).reshape((4, 5), order="F")
        >>> lats = np.arange(20).reshape((4, 5), order="C")
        >>> lines = np.array([2, 7, 12, 17])
        >>> cols = np.array([2, 7, 12, 17, 22])
        >>> hlines = np.arange(20)
        >>> hcols = np.arange(24)
        >>> satint = SatelliteInterpolator((lons, lats), (lines, cols), (hlines, hcols))
        >>> satint._fill_row_borders()
        >>> satint.x__
        array([[ 6381081.08333225,  6371519.34066148,  6328950.00792935,
                 6253610.69157758,  6145946.19489936],
               [ 6370997.        ,  6354509.6014956 ,  6305151.62592155,
                 6223234.99818839,  6109277.14889072],
               [ 6345786.79166939,  6311985.2535809 ,  6245655.67090206,
                 6147295.76471541,  6017604.5338691 ],
               [ 6270385.16249031,  6219684.08214232,  6137100.75832981,
                 6023313.2794414 ,  5879194.72399075],
               [ 6145476.82098957,  6078546.55734877,  5980676.23854351,
                 5852716.72120069,  5695705.57359808],
               [ 6095513.48438928,  6022091.54743135,  5918106.430629  ,
                 5784478.09790441,  5622309.91344102]])
        >>> satint.row_indices
        array([ 0,  2,  7, 12, 17, 19])
        >>> satint = SatelliteInterpolator((lons, lats), (lines, cols), (hlines, hcols), chunk_size=10)
        >>> satint._fill_row_borders()
        >>> satint.x__
        array([[ 6381081.08333225,  6371519.34066148,  6328950.00792935,
                 6253610.69157758,  6145946.19489936],
               [ 6370997.        ,  6354509.6014956 ,  6305151.62592155,
                 6223234.99818839,  6109277.14889072],
               [ 6345786.79166939,  6311985.2535809 ,  6245655.67090206,
                 6147295.76471541,  6017604.5338691 ],
               [ 6335702.70833714,  6294975.51441502,  6221857.28889426,
                 6116920.07132621,  5980935.48786045],
               [ 6320348.4990906 ,  6276139.09205974,  6199670.56624433,
                 6091551.90273768,  5952590.38414781],
               [ 6270385.16249031,  6219684.08214232,  6137100.75832981,
                 6023313.2794414 ,  5879194.72399075],
               [ 6145476.82098957,  6078546.55734877,  5980676.23854351,
                 5852716.72120069,  5695705.57359808],
               [ 6095513.48438928,  6022091.54743135,  5918106.430629  ,
                 5784478.09790441,  5622309.91344102]])
         >>> satint.row_indices
         array([ 0,  2,  7,  9, 10, 12, 17, 19])
        """
        lines = len(self.hrow_indices)
        chunk_size = self.chunk_size or lines

        x, y, z = [], [], []
        row_indices = []
        for index in range(0, lines, chunk_size):
            ties = np.argwhere(np.logical_and(self.row_indices >= index,
                                              self.row_indices < index
                                              + chunk_size)).squeeze()
            tiepos = self.row_indices[np.logical_and(self.row_indices >= index,
                                                     self.row_indices < index
                                                     + chunk_size)].squeeze()
            x.append(self._extrapolate_rows(self.x__[ties, :]))
            y.append(self._extrapolate_rows(self.y__[ties, :]))
            z.append(self._extrapolate_rows(self.z__[ties, :]))
            row_indices.append(np.array([self.hrow_indices[index]]))
            row_indices.append(tiepos)
            row_indices.append(np.array([self.hrow_indices[index
                                                           + chunk_size - 1]]))
        self.x__ = np.vstack(x)
        self.y__ = np.vstack(y)
        self.z__ = np.vstack(z)

        self.row_indices = np.concatenate(row_indices)
    
    def _interp(self):
        """Interpolate the cartesian coordinates.
        """
        xpoints, ypoints = np.meshgrid(self.hrow_indices,
                                       self.hcol_indices)
        spl = RectBivariateSpline(self.row_indices,
                                  self.col_indices,
                                  self.x__,
                                  s=0,
                                  kx=self.kx,
                                  ky=self.ky)

        self.newx = spl.ev(xpoints.ravel(), ypoints.ravel())
        self.newx = self.newx.reshape(xpoints.shape)

        spl = RectBivariateSpline(self.row_indices,
                                  self.col_indices,
                                  self.y__,
                                  s=0,
                                  kx=self.kx,
                                  ky=self.ky)

        self.newy = spl.ev(xpoints.ravel(), ypoints.ravel())
        self.newy = self.newy.reshape(xpoints.shape)

        spl = RectBivariateSpline(self.row_indices,
                                  self.col_indices,
                                  self.z__,
                                  s=0,
                                  kx=self.kx,
                                  ky=self.ky)

        self.newz = spl.ev(xpoints.ravel(), ypoints.ravel())
        self.newz = self.newz.reshape(xpoints.shape)

    def interpolate(self):
        """Do the interpolation, and return resulting longitudes and latitudes.
        """
        self._interp()

        self.longitude = get_lons_from_cartesian(self.newx, self.newy)
        self.longitude = self.longitude.reshape(len(self.hcol_indices),
                                                len(self.hrow_indices)).T

        self.latitude = get_lats_from_cartesian(self.newx, self.newy, self.newz)
        self.latitude = self.latitude.reshape(len(self.hcol_indices),
                                              len(self.hrow_indices)).T
        return self.longitude, self.latitude

def get_lons_from_cartesian(x__, y__):
    """Get longitudes from cartesian coordinates.
    """
    return rad2deg(arccos(x__ / sqrt(x__ ** 2 + y__ ** 2))) * sign(y__)
    
def get_lats_from_cartesian(x__, y__, z__, thr=0.8):
    """Get latitudes from cartesian coordinates.
    """
    # if we are at low latitudes - small z, then get the
    # latitudes only from z. If we are at high latitudes (close to the poles)
    # then derive the latitude using x and y:

    lats = np.where(np.logical_and(np.less(z__, thr * EARTH_RADIUS), 
                                   np.greater(z__, -1. * thr * EARTH_RADIUS)),
                    90 - rad2deg(arccos(z__/EARTH_RADIUS)),
                    sign(z__) *
                    (90 - rad2deg(arcsin(sqrt(x__ ** 2 + y__ ** 2)
                                         / EARTH_RADIUS))))
    return lats





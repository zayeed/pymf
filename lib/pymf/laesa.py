#!/usr/bin/python2.6
#
# Copyright (C) Christian Thurau, 2010. 
# Licensed under the GNU General Public License (GPL). 
# http://www.gnu.org/licenses/gpl.txt
#$Id: sivm.py 22 2010-08-13 11:16:43Z cthurau $
#$Author$
""" 
PyMF LAESA
"""

__version__ = "$Revision$"

import scipy.sparse
import numpy as np

from dist import *
from aa import AA

__all__ = ["LAESA"]

class LAESA(AA):
	"""  	
	SIVM(data, num_bases=4, niter=100, show_progress=True, compW=True)
	
	
	Simplex Volume Maximization. Factorize a data matrix into two matrices s.t.
	F = | data - W*H | is minimal. H is restricted to convexity. W is iteratively
	found by maximizing the volume of the resulting simplex (see [1]).
	
	Parameters
	----------
	data : array_like
		the input data
	num_bases: int, optional 
		Number of bases to compute (column rank of W and row rank of H). 
		4 (default)
	niter: int, optional
		Number of iterations of the alternating optimization.
		100 (default)
	show_progress: bool, optional
		Print some extra information
		False (default)
	compW: bool, optional
		Compute W (True) or only H (False). Useful for using basis vectors
		from another convexity constrained matrix factorization function
		(e.g. svmnmf) (if set to "True" niter can be set to "1")
	compH: bool, optional
		Compute H (True) or only H (False). Useful for using precomputed
		basis vectors.
	dist_measure: string, optional
		The distance measure for finding the next best candidate that 
		maximizes the simplex volume ['l2','l1','cosine','sparse_graph_l2']
		'l2' (default)
	optimize_lower_bound: bool, optional
		Use the alternative selection criterion that optimizes the lower
		bound (see [1])
		False (default)
	
	Attributes
	----------
		W : "data_dimension x num_bases" matrix of basis vectors
		H : "num bases x num_samples" matrix of coefficients
		
		ferr : frobenius norm (after applying .factoriz())		
	
	Example
	-------
	Applying LAESA to some rather stupid data set:
	
	>>> import numpy as np
	>>> data = np.array([[1.0, 0.0, 2.0], [0.0, 1.0, 1.0]])
	>>> laesa_mdl = LAESA(data, num_bases=2, niter=10)
	>>> laesa_mdl.initialization()
	>>> laesa_mdl.factorize()
	
	The basis vectors are now stored in laesa_mdl.W, the coefficients in laesa_mdl.H. 
	To compute coefficients for an existing set of basis vectors simply	copy W 
	to laesa_mdl.W, and set compW to False:
	
	>>> data = np.array([[1.5, 1.3], [1.2, 0.3]])
	>>> W = np.array([[1.0, 0.0], [0.0, 1.0]])
	>>> laesa_mdl = LAESA(data, num_bases=2, niter=1, compW=False)
	>>> laesa_mdl.initialization()
	>>> laesa_mdl.W = W
	>>> laesa_mdl.factorize()
	
	The result is a set of coefficients laesa_mdl.H, s.t. data = W * laesa_mdl.H.
	"""

	def __init__(self, data, num_bases=4, niter=100, show_progress=False, compW=True, compH=True, dist_measure='l2'):

		# call inherited method		
		AA.__init__(self, data, num_bases=num_bases, niter=niter, show_progress=show_progress, compW=compW)
			
		self._dist_measure = dist_measure	
		
		self._compH = compH

		
		# assign the correct distance function
		if self._dist_measure == 'l1':
				self._distfunc = l1_distance
				
		elif self._dist_measure == 'l2':
				self._distfunc = l2_distance
		elif self._dist_measure == 'cosine':
				self._distfunc = cosine_distance
				
		elif self._dist_measure == 'kl':
				self._distfunc = kl_divergence	
						
		elif self._dist_measure == 'sparse_graph_l2':
				self._distfunc = sparse_graph_l2_distance

	def _distance(self, idx):
			# compute distances of a specific data point to all
			# other samples			
			if scipy.sparse.issparse(self.data):
				step = self.data.shape[1]
			else:	
				step = 50000	
				
			d = np.zeros((self.data.shape[1]))		
			vec = self.data[:, idx:idx+1]	
			self._logger.info('compute distance to node ' + str(idx))									
			# slice data into smaller chunks
			for idx_start in range(0,self.data.shape[1],step):					
				if idx_start + step > self.data.shape[1]:
					idx_end = self.data.shape[1]
				else:
					idx_end = idx_start + step

				d[idx_start:idx_end] = self._distfunc(self.data[:,idx_start:idx_end], vec)
				self._logger.info('completed:' + str(idx_end/(self.data.shape[1]/100.0)) + "%")	
			
			return d
		
	def initialization(self):
			# Fastmap like initialization
			# set the starting index for fastmap initialization		
			cur_p = 0		
			
			# after 3 iterations the first "real" index is found
			for i in range(3):								
				d = self._distance(cur_p)		
				cur_p = np.argmax(d)

			self.select = []
			self.select.append(cur_p)	
			if self._compH:
				self.H = np.zeros((self._num_bases, self._num_samples))
				
			if self._compW:
				AA.initialization(self)

	def updateW(self):
		
		# initialize some of the recursively updated distance measures ....		
		distiter = self._distance(self.select[-1])				
		
		for l in range(self._num_bases-1):										
			d = self._distance(self.select[-1])								
		
			# replace distances in distiter
			distiter = np.where(d<distiter,d,distiter)
			
			# detect the next best data point
			self._logger.info('searching for next best node ...')					
			self.select.append(np.argmax(distiter))
			self._logger.info('cur_nodes: ' + str(self.select))

		# sort indices, otherwise h5py won't work
		self.W = self.data[:, np.sort(self.select)]
		# but "unsort" it again to keep the correct order
		self.W = self.W[:, np.argsort(np.argsort(self.select))]
		
	def factorize(self):
		"""Do factorization s.t. data = dot(dot(data,beta),H), under the convexity constraint
			beta >=0, sum(beta)=1, H >=0, sum(H)=1
		"""
		# compute new coefficients for reconstructing data points		
		if self._compW:
			self.updateW()
			
		if self._compH:			
			self.updateH()					
			
		self.ferr = np.zeros(1)
		if not scipy.sparse.issparse(self.data):
			self.ferr[0] = self.frobenius_norm()		
			self._logger.info('FN:' + str(self.ferr[0]))
					
if __name__ == "__main__":
	import doctest  
	doctest.testmod()	

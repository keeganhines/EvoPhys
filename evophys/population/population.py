'''
Genetic algorithm simulation
other documentation....
'''

import random
import numpy as np
import pandas as pd
from scipy.stats import norm


class PhysPopulation():
	'''
	A population of user-specified biophysical models
	'''

	def __init__(self,model,modelParams={},params_to_mut=[],N=100,dt=10,selection_strength=1,mutAllParams=True,startRandom=False,paramBounds=None):
		
		# Biophysical model
		# Create target model on startup by simulating under binding model and populating self.binding curve
		self.model = model
		self._model_params = modelParams
		self._model_inst = self.model(**modelParams)
		self.target = self._model_inst.output
		
		self.params_to_mut = params_to_mut # params in model to explore. Must specify so some can be left static
		self._validate_params()
		self.param_means = {i:None for i in self._model_inst.paramD}
		self.param_vars = {i:None for i in self._model_inst.paramD}

		
		# Population parameters
		self.population = []
		self.mean_fitness = 0
		self.fitness_var = 0
		
		# Genetic algorithm params
		self.N = N
		self.selection_strength = selection_strength
		self.mutAllParams = mutAllParams
		
		# Brownian motion params
		self.dt = dt
		
		# Initialization
		self.param_bounds = paramBounds
		self._initialize_pop(startRandom)
		
		
	def _validate_params(self):
		for i in self.params_to_mut:
			assert i in self._model_inst.paramD, "Parameter %s not found in supplied model" % i
		
	def _update_biophys_params(self):
		'''Update means and variances for population K1 and K2s'''
		paramVals = {p:[] for p in self._model_inst.paramD}
		ws = []
		for i in self.population:
			for param in self._model_inst.paramD.keys():
				paramVals[param].append(i.paramD[param])
			ws.append(i.w)
			
		for p in self._model_inst.paramD:
			self.param_means[p] = sum(paramVals[p])/len(paramVals[p])
			self.param_vars[p] = np.var(paramVals[p])
			
		self.mean_fitness = sum(ws)/len(ws)
		self.fitness_var = np.var(ws)
		
	def _initialize_pop(self,startRandom=False):
		'''Create starting population of size self.N filled with Adair models, each sampled'''
		
		self.population = []
		paramVals = {p:[] for p in self._model_inst.paramD}
		ws = []
		
		for i in range(self.N):
			if startRandom:
				rando = np.random.uniform
				for param in self._model_inst.paramD:
					assert self.param_bounds and param in self.param_bounds, "Must supply bounds for parameter random start"
				kwargs = {p: np.random.uniform(self.param_bounds[p][0],self.param_bounds[p][1]) for p in self.param_bounds}
				newModel = self.model(**kwargs)
			else:
				newModel = self.model(**self._model_params)
			
			newModel.w = self._get_w(self.target,newModel.output)
			
			for param in self._model_inst.paramD:
				paramVals[param].append(newModel.paramD[param])
			ws.append(newModel.w)
			
			self.population.append(newModel)
			
		for p in self._model_inst.paramD:
			self.param_means[p] = sum(paramVals[p])/len(paramVals[p])
			self.param_vars[p] = np.var(paramVals[p])

		self.mean_fitness = sum(ws)/len(ws)
		self.fitness_var = np.var(ws)

	def _get_w(self,target,comp):
		'''
		Compute fitness function. Fitness is modeled as a normal with x-mu = rmsd between
		target model output and focal, and var = self.selection_strength. 
		'''
		assert len(comp) == len(target), "Different vector lengths: target: %i, comp: %i" % (len(target),len(comp))
		rmsd = np.sqrt(sum(map(lambda (x,y): (x-y)**2, zip(target,comp)))/len(comp))
		return np.exp(-(rmsd**2)/2*self.selection_strength)

	def brownian(self,paramD):
		'''Take a single brownian step over params vector'''
		out = {}
		if not self.mutAllParams:
			paramToMut = np.random.choice(self.params_to_mut)
		for i,j in paramD.iteritems():
			if i not in self.params_to_mut:
				out[i] = j # set to old value
				continue
			elif not self.mutAllParams and i != paramToMut:
				out[i] = j # set to old value
				continue
			else:
				new_param = j + norm.rvs(loc=0,scale=2*self.dt)
				if new_param < 0:
					new_param = 0
				out[i] = new_param
		return out
		
	def procreate(self):
		newpop = []
		paramVals = {p:[] for p in self._model_inst.paramD}
		ws = []
		
		for model in self.population:
			kwargs = self.brownian(model.paramD)
			newModel = self.model(**kwargs)
			
			newModel.w = self._get_w(self.target,newModel.output)
			
			for param in self._model_inst.paramD:
				paramVals[param].append(newModel.paramD[param])
			ws.append(newModel.w)
			
			newpop.append(newModel)
			
		self.population = newpop
			
		for p in self._model_inst.paramD:
			self.param_means[p] = sum(paramVals[p])/len(paramVals[p])
			self.param_vars[p] = np.var(paramVals[p])
			
		self.mean_fitness = sum(ws)/len(ws)
		self.fitness_var = np.var(ws)
		
	def select(self):
		fitness_vec = [m.w for m in self.population]
		w_sum = sum(fitness_vec)
		w_norm = [i/w_sum for i in fitness_vec]
		new_pop = np.random.choice(self.population,self.N,p=w_norm)
		self.population = new_pop
		self._update_biophys_params()
		
		
		
class WrightFisherSim:

	def __init__(self,model,modelParams={},N=10e5,mu=10e-5,dt=10,selection_strength=.1):
	
		self.model = model
		self._model_params = modelParams
		self._model_inst = self.model(**modelParams)
		# list for choosing num params to mutate range 1..#numModelParams
		self._numParamList = [i+1 for i in np.arange(len(self._model_params))]
		self.target = self._model_inst.output
		self.output = self.target
		
		# PopGen parameters
		self.mu = mu # mutation rate
		self.dt = dt
		self.N = N
		self.current_params = modelParams
		self.fitness = 1
		self.selection_strength = selection_strength
		self.current_gen = 1
		
		# Current state
		self._isFirst = True
		self.gens_till_next_mut = 1
		self.gens_since_mut = 1
		self.mutated = False
		self.num_params_mutated = 0
		self.params_mutated = []
		self.new_model_w = 0
		self.new_model_s = 0
		self.prob_fix = 0
		self.fixed = False
		
	def _num_gens_till_mut(self):
		'''Introduction of new mutations is a Poisson process with wait time ~ Exp( lambda = 4Nmu )'''
		return random.expovariate(4 * self.N * self.mu)
		
	def _fitness_function_normal(self,target,comp,selection_strength):
		'''Compute rmsd between two input binding curves and return a normally 
		distributed fitness function with variance parameter self.selection_strength'''
		assert len(comp) == len(target)
		rmsd = np.sqrt(sum(map(lambda (x,y): (x-y)**2, zip(target,comp)))/len(target))
		return np.exp(-(rmsd**2)/2*selection_strength)
		
	def _selection_coefficient(self,w):
		return (w/self.fitness) - 1
		
	def _prob_fix(self,s):
		return (1 - np.exp(-(2 * s))) / (1 - np.exp(-(4 * self.N * s)))
		
	def nextGen(self):
		
		if self._isFirst:
			# pull num generations until mutation from exponential(4Nmu)
			self.gens_till_next_mut = self._num_gens_till_mut()
			self._isFirst = False
		
		# if gens generations < num until mut. write current state
		if self.gens_till_next_mut <= self.gens_since_mut:
		
			self.mutated = True
			
			# if mutation, get kind of mutation from uniform over how many parameters to disturb (1,2,3)
			self.num_params_mutated = random.choice(self._numParamList)
			
			# Choose a number <self.num_params_mutated> of parameter names to mutate
			self.params_mutated = random.sample(self.current_params.keys(),self.num_params_mutated)
			newParamD = self.current_params.copy()
			
			# mutate parameters using normal (mean=0,dt)
			for p in self.params_mutated:
				# overwrite old params with new
				newP = self.current_params[p] + random.normalvariate(0,2*self.dt)
				if newP < 0:
					newP = 0
				newParamD[p] = newP

			newModel = self.model(**newParamD)
			
			# Calculate fitness
			self.new_model_w = self._fitness_function_normal(self.target,newModel.output,self.selection_strength)
			
			# calculate selection coefficient
			self.new_model_s = self._selection_coefficient(self.new_model_w)
			
			# calc prob of fixation
			self.prob_fix = self._prob_fix(self.new_model_s)
			
			# draw random(0,1), if < prob of fixation, set new model as current, with parameters and fitness values.
			rando = random.uniform(0,1)
			self.fixed = rando < self.prob_fix
			if self.fixed:
				self.current_params = newModel.paramD # set to new params
				self.output = newModel.output # set to new output
				self.fitness = self.new_model_w
				
			self.gens_till_next_mut = self._num_gens_till_mut()
			
		else:
			self.mutated = False
			self.num_params_mutated = 0
			self.fixed = False
			self.gens_since_mut += 1
		
		self.current_gen += 1
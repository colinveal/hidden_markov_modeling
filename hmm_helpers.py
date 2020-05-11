"""
Helpers for HMM
"""

import json
from pomegranate import*

from exceptions import Error

def build_hmm(hmm_file):
  """


  Parameters
  ----------
  jsonfile : TYPE
    DESCRIPTION.

  Returns
  -------
  None.

  """

  with open(hmm_file) as json_file:
    hmm_json_map = json.load(json_file)
    hmm_json_map = json.loads(hmm_json_map)


    hmm = HiddenMarkovModel(name=hmm_json_map["name"],
                            start=None, end=None)

    # reade in the states
    states = hmm_json_map["states"]
    distribution_ties = hmm_json_map.get("distribution ties",None)
    hmm, hmm_states = build_states(hmm=hmm,
                                   states=states,
                                   distribution_ties=distribution_ties)#hmm_json_map["distribution ties"])

    hmm.start = hmm_states[hmm_json_map['start_index']]
    hmm.end = hmm_states[hmm_json_map['end_index']]

    # Add all the edges to the model
    for start, end, probability, pseudocount, group in hmm_json_map['edges']:
      hmm.add_transition(hmm_states[start], hmm_states[end], probability,
                         pseudocount, group)

    hmm.bake(verbose=True)
    return hmm


def build_edges(edges):
  pass

def build_states(hmm, states, distribution_ties):

  state_objs = []
  for state in states:

      print("Working with state: ", state["name"])
      #print(state)
      state_obj = build_state(state_map=state)

      if state_obj is not None:
        state_objs.append(state_obj)


  if distribution_ties is not None:
    for i, j in distribution_ties:
    # Tie appropriate states together
      states[i].tie(states[j])
    hmm.add_states(state_objs)
  return hmm, state_objs


def build_state(state_map):

  name = state_map["name"]
  weight = state_map["weight"]
  dist_map = state_map["distribution"]

  if dist_map is not None:

    dist_name = dist_map["name"]

    # the state has IndependentComponentsDistribution
    # as a distribution. In this case we have more
    # than one parameters unless we deal with a GMM
    # that wraps the components
    if dist_name == "IndependentComponentsDistribution":
      parameters = dist_map["parameters"]

      dist_param  = parameters[0]

      components = []

      for param in dist_param:


        if param["class"] == "GeneralMixtureModel":
          #json_str = json.dumps(param["distributions"])

          # get the distributions list for this
          # GMM
          distributions = param["distributions"]
          dist_list = []

          for dist in distributions:
            distribution = Distribution.from_json(json.dumps(dist))
            dist_list.append(distribution)

          weights = param["weights"]
          gmm = GeneralMixtureModel(dist_list, weights=weights)
          components.append(gmm)
        elif param["class"] == "Distribution":
          distribution = Distribution.from_json(json.dumps(param))

          components.append(distribution)


      # now that we collected the independent components
      # construct the state
      return State(IndependentComponentsDistribution(components),
                   name=name, weight=weight )
  else:

    #this means that the state has
    return State(None, name=name, weight=weight)


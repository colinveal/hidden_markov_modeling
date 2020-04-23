import argparse
import logging
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import csv
from pomegranate import*

from helpers import read_configuration_file
from helpers import set_up_logger
from helpers import save_hmm
from helpers import flat_windows
from helpers import flat_windows_from_state
from helpers import HMMCallback
from helpers import print_logs_callback
from helpers import flat_windows_rd_from_indexes
from helpers import MixedWindowView
from helpers import INFO
from analysis_helpers import save_clusters
from analysis_helpers import save_windows_statistic

from bam_helpers import extract_windows
from cluster import Cluster
from cluster import clusters_statistics
from hypothesis_testing import SignificanceTestLabeler
from preprocess_utils import fit_distribution
from preprocess_utils import compute_statistic
from preprocess_utils import build_clusterer
from preprocess_utils import remove_outliers
from exceptions import Error


def create_clusters(windows, configuration):

  kwargs = {"clusterer":{ "name":configuration["clusterer"],
                          "config":configuration["clusterer"]["config"]}}


  # create the clusters
  clusterer, initial_index_medoids = build_clusterer(data=windows,
                                                      nclusters=len(configuration["states"]),
                                                      method="kmedoids",
                                                      **kwargs)

  print("{0} Initial medoids indexes: {1}".format(INFO, initial_index_medoids))

  # get the window indexes
  clusters_indexes = clusterer.get_clusters()
  clusters = []

  for i in range(len(clusters_indexes)):
    clusters.append(Cluster(id_ = i, indexes=clusters_indexes[i]))

  #cluster_stats = clusters_statistics(clusters=clusters, windows=windows)
  #print("Cluster statistics (before labeling): ")
  #print(cluster_stats)

  print("{0} Saving cluster indices".format(INFO))
  save_clusters(clusters=clusters, windows=windows, statistic="mean")


  """
  labeler = SignificanceTestLabeler(clusters=clusters,
                                    windows=windows)

  labeled_clusters = labeler.label(test_config=configuration["labeler"])

  print("Finished cluster labeling...")

  # update windows states according
  # to the cluster label they live in
  for state in labeled_clusters:
    cluster = labeled_clusters[state]
    indexes = cluster.indexes

    for idx in indexes:
      windows[idx].set_state(cluster.state)

  return labeled_clusters
  """


def init_hmm(clusters, windows, configuration):

  # create the HMM
  hmm_model = HiddenMarkovModel(name=configuration["HMM"]["name"],
                                start=None, end=None)


  state_to_dist = {}
  states = []
  for cluster in clusters:
    state_to_dist[cluster.state.name] = \
    fit_distribution(data=cluster.get_data_from_windows(windows=windows),
                     dist_name=configuration["fit_states_dist"][cluster.state.name])
    states.append(State(state_to_dist[cluster.state.name], name=cluster.state.name))

    print("For cluster: {0}".format(cluster.state.name))
    print("Distribution:")
    print(state_to_dist[cluster.state.name])


  # add the states to the model
  hmm_model.add_states(states)

  # construct the transition matrix.
  # We create a dense HMM with equal
  # transition probabilities between each state
  # this will be used for initialization when
  # we fit the model. All states have an equal
  # probability to be the starting state or we could

  if len(clusters) == 1:
    hmm_model.add_transition(hmm_model.start, states[0], 1.0)
  else:

    for i, cluster in enumerate(clusters):
      hmm_model.add_transition(hmm_model.start,
                             states[i],
                              configuration["HMM"]["start_prob"][cluster.state.name])

  for i in states:
    for j in states:

      if i == j:
        # high probabiity for self-transitioning
        hmm_model.add_transition(i, j, 0.95)
      else:

        #low probability for change state transition
        hmm_model.add_transition(i, j, 0.05)

  # finally we need to bake
  hmm_model.bake(verbose=True)
  return hmm_model

def hmm_train(clusters, windows, configuration):

  print("Start HMM training....")

  # initialize the model
  hmm_model = init_hmm(clusters=clusters,
                       windows=windows,
                       configuration=configuration)


  #flatwindows = [flat_windows_from_state(windows=windows,
  #                                      configuration=configuration,
  #                                      as_on_seq=False)]

  flatwindows = flat_windows(windows=windows)

  #print("Flatwindows are: ", flatwindows)


  # fit the model
  hmm_model, history = hmm_model.fit(sequences=flatwindows,
                                           #min_iterations=,
                                           algorithm=configuration["HMM"]["train_solver"],
                                           return_history=True,
                                           verbose=True,
                                           lr_decay=0.6,
                                           callbacks=[HMMCallback(callback=print_logs_callback)],
                                           inertia=0.01)

  print("Done training HMM")
  hmm_model.bake()

  p_d_given_m = hmm_model.log_probability(sequence=flatwindows[0])
  print("P(D|M): ", p_d_given_m)
  print(hmm_model.predict_proba(flatwindows[0]))
  viterbi_path=hmm_model.viterbi(flatwindows[0])
  trans, ems = hmm_model.forward_backward( flatwindows[0] )

  print("Tansition matrix")
  print(trans)

  print("Emission matrix")
  print(ems)

  # plot the model
  #plt.figure( figsize=(10,6) )
  #hmm_model.plot()
  #plt.show()


  save_hmm(hmm_model=hmm_model,
                   configuration=configuration,
                   win_interval_length=0)


def make_windows(configuration):

    wga_start_idx = configuration["test_file"]["start_idx"]
    wga_end_idx = configuration["test_file"]["end_idx"]

    if wga_end_idx == "none":
      wga_end_idx = None
    else:
      wga_end_idx = int(wga_end_idx)

    windowsize = configuration["window_size"]
    chromosome = configuration["chromosome"]

    print("{0} Start index used: {1}".format(INFO, wga_start_idx))
    print("{0} End index used: {1}".format(INFO,wga_end_idx))
    print("{0} Window size: {1}".format(INFO, windowsize))
    print("{0} Chromosome: {1}".format(INFO, chromosome))

    args = {"start_idx": int(wga_start_idx),
            "end_idx": wga_end_idx,
            "windowsize": int(windowsize)}

    if "quality_theshold" in configuration:
      args["quality_theshold"] = configuration["quality_theshold"]

    try:

        print("{0} Creating WGA Windows...".format(INFO))
        # extract the windows for the WGA treated file
        wga_windows = extract_windows(chromosome=chromosome,
                                      ref_filename=configuration["reference_file"]["filename"],
                                      test_filename=configuration["test_file"]["filename"],
                                      **args)

        if len(wga_windows) == 0:
            raise Error("WGA windows have not been created")
        else:
            print("{0} Number of WGA windows: {1}".format(INFO, len(wga_windows)))


        print("{0} Creating No WGA Windows...".format(INFO))
        non_wga_start_idx = configuration["no_wga_file"]["start_idx"]
        non_wga_end_idx = configuration["no_wga_file"]["end_idx"]

        args = {"start_idx": int(non_wga_start_idx),
                "end_idx": (non_wga_end_idx),
                "windowsize": int(windowsize)}

        # exrtact the non-wga windows
        non_wga_windows = extract_windows(chromosome=chromosome,
                                          ref_filename=configuration["reference_file"]["filename"],
                                          test_filename=configuration["no_wga_file"]["filename"],
                                          **args)

        if len(non_wga_windows) == 0:
            raise Error("Non-WGA windows have not  been created")
        else:
            print("{0} Number of non-wga windows: {1}".format(INFO, len(non_wga_windows)))


        # zip mixed windows the smallest length
        # prevails
        mixed_windows = []

        for win1, win2 in zip(wga_windows, non_wga_windows):
          mixed_windows.append(MixedWindowView(wga_w=win1,
                                               n_wga_w=win2))

        print("{0} Number of mixed windows: {1}".format(INFO,len(mixed_windows)))

        # compute the global statistics of the windows
        wga_rds = []
        no_wga_rds = []

        for window in mixed_windows:
          wga_rds.extend(window.get_rd_counts(name="wga_w"))
          no_wga_rds.extend(window.get_rd_counts(name="n_wga_w"))

        wga_statistics = compute_statistic(data=wga_rds, statistics="all")
        no_wga_statistics = compute_statistic(data=no_wga_rds, statistics="all")

        print("{0} WGA stats: {1}".format(INFO, wga_statistics))
        print("{0} No WGA stats: {1}".format(INFO, no_wga_statistics))

        save_windows_statistic(windows=mixed_windows, statistic="mean")


        # do the outlier removal

        if "outlier_remove" in configuration and\
          configuration["outlier_remove"]:

          config = configuration["outlier_remove"]["config"]
          config["statistics"] = {"n_wga_w": no_wga_statistics,
                                  "wga_w":wga_statistics}

          mixed_windows = remove_outliers(windows=mixed_windows,
                          removemethod=configuration["outlier_remove"]["name"],
                          config=config)

          print("{0} Number of windows after outlier removal: {1}".format(INFO,
                                                                          len(mixed_windows)))
        else:
          print("{0} No outlier removal performed".format(INFO))


        return mixed_windows

    except KeyError as e:
        logging.error("Key: {0} does not exit".format(str(e)))
        raise
    except Error as e:
        logging.error(str(e))
        raise
    except Exception as e:
        logging.error("Unknown exception occured: " + str(e))
        raise

def main():

    print("{0} Starting analysis".format(INFO))
    description = "Check the README file for information on how to use the script"
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--config', type=str, default='config.json',
                        help='You must specify a json formatted configuration file')
    args = parser.parse_args()

    config_file = args.config
    configuration = read_configuration_file(config_file)

    # configure the logger to use
    set_up_logger(configuration=configuration)
    logging.info("Checking if logger is sane...")

    print("{0} Creating windows...".format(INFO))
    mixed_windows = make_windows(configuration=configuration)

    print("{0} Done...".format(INFO))
    print("{0} Start clustering....".format(INFO))

    wga_clusters = create_clusters(windows=mixed_windows,
                                   configuration=configuration)

    print("{0} Done...".format(INFO))
    #print("Number of wga_clusters used: {0}".format(len(wga_clusters)))

    #for cluster in wga_clusters:
    #  print("State modelled by cluster {0} is {1}".format(wga_clusters[cluster].cidx,
    #                                                      wga_clusters[cluster].state.name))
    #  print("Cluster statistics: ")
    #  print(wga_clusters[cluster].get_statistics(windows=wga_windows,
    #                                             statistic="all"))

    #hmm_train(clusters=wga_clusters.values(),
    #          windows=wga_windows,
    #          configuration=configuration)

    print("{0} Finished analysis".format(INFO))


if __name__ == '__main__':
    main()

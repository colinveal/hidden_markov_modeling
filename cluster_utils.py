import numpy as np
from pomegranate import *
from exceptions import Error
from helpers import INFO
from helpers import WindowType,  WindowState
from preprocess_utils import get_distributions_list_from_names


def label_clusters(clusters, method, **kwargs):

    labeler = kwargs["labeler"]
    if method == "mean_diff":

        print("{0} Labeler: {1}".format(INFO, method))

        for cluster in clusters:

            print("{0} Cluster {1}".format(INFO, cluster.cidx))

            mu_wga = cluster.get_statistics(statistic="mean",
                                            window_type=WindowType.WGA)


            mu_no_wga = cluster.get_statistics(statistic="mean",
                                               window_type=WindowType.NO_WGA)

            print("{0} Cluster WGA mean: {1}".format(INFO, mu_wga))
            print("{0} Cluster NO WGA mean: {1}".format(INFO, mu_no_wga))

            if mu_wga >= labeler["tuf_mean_min"] and mu_wga <= labeler["tuf_mean_max"]:

                # this is potential tuf
                if np.fabs(mu_no_wga - mu_wga) > 5.0:
                    cluster.state = WindowState.TUF
                else:
                    cluster.state = WindowState.OTHER

            elif mu_wga < labeler["tuf_mean_min"] and mu_no_wga < labeler["tuf_mean_min"]:
                cluster.state = WindowState.DELETE

            else:
                cluster.state = WindowState.OTHER

            print("{0} Cluster state is {1}".format(INFO, cluster.state.name))

    return clusters



def build_cluster_mean_and_std(clusters, **kwargs):
 
    for cluster in clusters:

      indeces = cluster.indexes

      wga_data = np.empty((1,0), float)
      no_wga_data = np.empty((1,0), float)
      windows = cluster.windows

      for idx in indeces:
        window = windows[idx]
        if window.is_n_window() == False:
          mu1, mu2 = window.get_rd_stats(statistics="mean",
                                         name=WindowType.BOTH)

          wga_data = np.append(wga_data, np.array(mu1))
          no_wga_data = np.append(no_wga_data, np.array(mu2))


      # collected the data create the GMM for each
      # component in the cluster
      wga_params={"mean": np.mean(wga_data),
                  "std": np.std(wga_data)}

      no_wga_params={"mean": np.mean(no_wga_data),
                     "std": np.std(no_wga_data)}

      cluster.wga_mean = np.mean(wga_data)
      cluster.wga_std = np.std(wga_data)
      cluster.no_wga_mean = np.mean(no_wga_data)
      cluster.no_wga_std = np.std(no_wga_data)


def build_cluster_densities(clusters, **kwargs):

      config = kwargs["config"]

      for cluster in clusters:

        clust_dists = config["distributions"][cluster.state.name]

        # collected the data create the GMM for each
      # component in the cluster
        wga_params={"mean": cluster.wga_mean,
                    "std": cluster.wga_std}

        no_wga_params={"mean": cluster.no_wga_mean,
                       "std": cluster.no_wga_std}

        if cluster.state.name == 'TUF':
          wga_params["uniform_params"] = config["distributions"]["TUF"]["uniform_params"]
          no_wga_params["uniform_params"] = config["distributions"]["TUF"]["uniform_params"]

        if config["distributions"][cluster.state.name]["type"] == "gmm":
          wga_gmm = \
              GeneralMixtureModel(get_distributions_list_from_names(clust_dists["dists"],
                                                                     wga_params),
                                  weights=config["distributions"][cluster.state.name]["weights"])

          cluster.wga_density = wga_gmm

          non_wga_density = \
              GeneralMixtureModel(get_distributions_list_from_names(clust_dists["dists"],
                                                               no_wga_params),
                                  weights=config["distributions"][cluster.state.name]["weights"] )

          cluster.no_wga_density = non_wga_density

        elif config["distributions"][cluster.state.name]["type"] == "distribution":
          wga_dist = get_distributions_list_from_names(clust_dists["dists"],
                                                       wga_params)[0]
          cluster.wga_density = wga_dist

          non_wga_density = get_distributions_list_from_names(clust_dists["dists"],
                                                              no_wga_params)[0]
          cluster.no_wga_density = non_wga_density

      else:
        raise Error("Invalid cluster distribution method")

      return clusters


def clusters_statistics(clusters):
  """
  Claculate various statistics for the windows
  clustered in clusters

  Parameters
  ----------
  clusters : list of lists
    Contains the clustered window indexes. There are
    len(clusters) clusters
  windows : list of Window objects
    DESCRIPTION.

  Returns
  -------
  a map with the calculated statistics for each
  cluster

  """

  statistics = {}

  for c in range(len(clusters)):

    statistics[c] = clusters[c].get_statistics(statistic="all")
  return statistics


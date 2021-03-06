import torch
import torch_geometric
import RNA
from utils.rna_lib import init_graph, get_graph, act, seq_onehot2Base, get_distance_from_graph_norm, get_subgraph_exist
import pathos.multiprocessing as pathos_mp
import gym
from functools import partial
import numpy as np


def fetch_items(list, index):
    """
    fetch the elements from the list with the index of aims
    :param list: original list
    :param index: index of aims
    :return: the aims
    """
    return [list[i] for i in index]


class Env_RNA(gym.Env):
    def __init__(self, dotB_list, action_space, h_weight, pool=None, do_skip=True, observe='all'):
        """
        RNA设计环境
        :param dotB_list:
        :param action_space:
        :param h_weight:
        :param pool:
        :param do_skip:
        :param observe:
        """
        super(Env_RNA, self).__init__()
        if pool is None:
            self.pool = pathos_mp.ProcessPool()
        else:
            self.pool = pool
        self.dotB_list = dotB_list
        self.graphs = []
        self.action_space = action_space
        self.h_weight = h_weight
        self.id_list = list(range(len(dotB_list)))
        self.len_list = []
        self.do_skip = do_skip
        self.observe = observe
        self.max_len = 0

    def reset(self, init_len=1):
        gen_work = partial(get_graph, h_weight=self.h_weight)
        self.graphs = self.pool.map(gen_work, self.dotB_list)
        init_work = partial(init_graph, init_len=init_len, action_space=self.action_space)
        self.graphs = self.pool.map(init_work, self.graphs)
        self.len_list = [len(graph.y['dotB']) for graph in self.graphs]
        self.max_len = max(self.len_list)

        if self.observe == 'sub':
            observe_work = partial(get_subgraph_exist, aim_node=init_len)
            observe_graph_list = self.pool.map(observe_work, self.graphs)
            observe_graphs = torch_geometric.data.Batch.from_data_list(observe_graph_list)
        else:
            observe_graphs = torch_geometric.data.Batch.from_data_list(self.graphs).clone()

        return observe_graphs

    def step(self, actions, ep):
        step_work = partial(self.act_, ep=ep, action_space=self.action_space, do_skip=self.do_skip)
        step_result = self.pool.map(step_work, self.graphs, actions)
        step_result = list(step_result)
        step_result = list(zip(*step_result))
        self.graphs = list(step_result[0])
        reward_list = list(step_result[1])
        finished_list = list(step_result[2])
        skip_list = list(step_result[3])

        if self.observe == 'sub':
            if ep == self.max_len - 1:
                ep_ = ep
            else:
                ep_ = ep + 1
            observe_work = partial(get_subgraph_exist, aim_node=ep_)
            observe_graph_list = self.pool.map(observe_work, self.graphs)
        else:
            observe_graph_list = torch_geometric.data.Batch.from_data_list(self.graphs).clone().to_data_list()

        return observe_graph_list, reward_list, finished_list, skip_list

    @classmethod
    def act_(cls, graph, action, ep, action_space, do_skip):
        graph, skip = act(graph, action, ep, action_space, do_skip=do_skip)
        reward = 0
        finished = 0
        if ep == len(graph.y['dotB']) - 1:
            finished = 1
            seq_base = seq_onehot2Base(graph.x)
            graph.y['seq_base'] = seq_base
            dist_norm = get_distance_from_graph_norm(graph)
            reward = 1 - dist_norm
        return graph, reward, finished, skip

    def remove_graph(self, finish_index): # finish_id_list):
        # finish_index = np.where(np.array(self.id_list) == np.array(finish_id_list)[:, None])[-1]
        # remove_id_list = finish_id_list
        remove_id_list = fetch_items(self.id_list, finish_index)
        remove_graph_list = fetch_items(self.graphs, finish_index)
        self.graphs = [self.graphs[i] for i in range(len(self.graphs)) if i not in finish_index]
        self.id_list = [self.id_list[i] for i in range(len(self.id_list)) if i not in finish_index]
        return remove_id_list, remove_graph_list

    def get_index_ep(self, place):
        len_list = [1] + self.len_list[:-1]
        index_list = [len_list[i]+place-1 for i in range(len(self.len_list))]
        index = torch.tensor(index_list)
        return index




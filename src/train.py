import gym
from gym.spaces import Box
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import random
from copy import deepcopy

from model import *
from replay_buffer import *
from visualize import *
from util import *
import yaml
import sys
import datetime
import pickle

with open(sys.argv[1], "r") as f:
    config = yaml.safe_load(f)

algo_name = config['algo_name']
print(algo_name)
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
print(device)

env = gym.make(config['env'])

epsilon = int(config['model_params']['epsilon'])
gamma = int(config['model_params']['gamma'])
#Proportion of network you want to keep
tau = .995
random.seed(5714149178)


if algo_name == 'DQN-CNN':
    q = Q_CNN(env,device).to(device)
    q_target = Q_CNN(env, device).to(device)
elif algo_name == 'DQN-FC':
    q = Q_FC(env,device).to(device)
    q_target = Q_FC(env, device).to(device)
elif algo_name == 'DQN-Single':
    q = Q_Single(env,device).to(device)
    q_target = Q_Single(env, device).to(device)



optimizer = torch.optim.Adam(q.parameters(), lr=int(float(config['model_params']['lr'])))
max_ep = int(config['max_ep'])

batch_size = int(config['batch_size'])
rb = ReplayBuffer(int(float(config['replay_buffer_size'])))

def resume(m, repb):
    #load the model and rb
    with open(repb, 'rb') as f:
        rb = pickle.load(f)
    q.load_state_dict(torch.load(m))
    q_target = deepcopy(q)
    train()

#Training the network
def train():
    explore(int(config['exploration']))
    ep = 0
    while ep < max_ep:
        s = env.reset()
        ep_r = 0
        while True:
            with torch.no_grad():
                #Epsilon greed exploration
                if random.random() < epsilon:
                    a = env.action_space.sample()
                else:
                    if algo_name == 'DQN-CNN':
                        gp_s = torch.tensor(np.array(s, copy=False)).view(1,1,s.shape[0]).to(device)
                    else:
                        gp_s = torch.tensor(np.array(s, copy=False)).to(device)

                    a = int(np.argmax(q(gp_s).cpu()))

            #Get the next state, reward, and info based on the chosen action

            s2, r, done, _ = env.step(int(a))
            rb.store(s, a, r, s2, done)
            ep_r += r

            #If it reaches a terminal state then break the loop and begin again, otherwise continue
            if done:
                update_viz(ep, ep_r, algo_name)
                ep += 1
                break
            else:
                s = s2

            update()
        if ep % int(config['save_interval']) == 0 and eq != 0:
            fn = config['env'] + '_' + algo_name + datetime.datetime.now().strftime("%Y-%m-%d::%H:%M:%S")
            torch.save(q.state_dict(), config['model_save_path'] + fn  + '.pt')
            with open(fn + '.pickle', 'wb') as f:
                pickle.dump(rb, f)


#Updates the Q by taking the max action and then calculating the loss based on a target
def update():
    s, a, r, s2, m = rb.sample(batch_size)

    states = torch.tensor(s).to(device)
    actions = torch.tensor(a).to(device)
    rewards = torch.tensor(r).to(device)
    states2 = torch.tensor(s2).to(device)
    masks = torch.tensor(m).to(device)

    with torch.no_grad():
        if algo_name == 'DQN-CNN':
            max_next_q, _ = torch.max(q_target(states2.view(states2.shape[0],1,states2.shape[1])),dim=1, keepdim=True)
        else:
            max_next_q, _ = torch.max(q_target(states2),dim=1, keepdim=True)
        y = rewards + masks*gamma*max_next_q

    if algo_name == 'DQN-CNN':
        loss = F.mse_loss(torch.gather(q(states.view(states.shape[0],1,states.shape[1])), 1, actions.long()), y)
    else:
        loss = F.mse_loss(torch.gather(q(states), 1, actions.long()), y)

    #Update q
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

    #Update q_target
    for param, target_param in zip(q.parameters(), q_target.parameters()):
        target_param.data = target_param.data*tau + param.data*(1-tau)

#Explores the environment for the specified number of timesteps to improve the performance of the DQN
def explore(timestep):
    ts = 0
    while ts < timestep:
        s = env.reset()
        while True:
            a = env.action_space.sample()
            s2, r, done, _ = env.step(int(a))
            rb.store(s, a, r, s2, done)
            ts += 1
            if done:
                break
            else:
                s = s2


train()

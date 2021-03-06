from torch import nn
from .optimizers import get_optimizer
import torch 
from src import models
from torch.nn import functional as F
import itertools 
import tqdm
from haven import haven_utils as hu
import os 
import numpy as np
from src import utils as ut
import torch.optim as optim


from .base_netC import resnet_meta, resnet_meta_2
import torchvision.models as models

from torchmeta.modules import MetaSequential, MetaLinear
from torchmeta.modules import DataParallel

class Classifier(nn.Module):
    def __init__(self, model_dict, dataset, device):
        super().__init__()
        
        self.dataset = dataset

        self.model_dict = model_dict
        if self.model_dict['name'] == 'resnet18':
            if self.model_dict['pretrained']:
                self.net = models.resnet18(pretrained=True)
                self.net.fc = nn.Linear(512, self.dataset.n_classes)
            else:
                self.net = models.resnet18(num_classes= self.dataset.n_classes)
                
        elif self.model_dict['name'] == 'resnet18_meta':
            if self.model_dict.get('pretrained', True):
                self.net = resnet_meta.resnet18(pretrained=True)
                self.net.fc = MetaLinear(512, self.dataset.n_classes)
            else:
                self.net = resnet_meta.resnet18(num_classes= self.dataset.n_classes)
        elif self.model_dict['name'] == 'resnet18_meta_2':
                self.net = resnet_meta_2.ResNet18(nc=3, nclasses= self.dataset.n_classes)                

        elif self.model_dict['name'] == 'resnet18_meta_old':
                self.net = resnet_meta_old.ResNet18(nc=3, nclasses= self.dataset.n_classes)

        else:
            raise ValueError('network %s does not exist' % model_dict['name'])

        if (device.type == 'cuda'):
            self.net = DataParallel(self.net)
        self.net.to(device)
        # set optimizer
        self.opt_dict = model_dict['opt']
        self.lr_init = self.opt_dict['lr']
        if self.model_dict['opt']['name'] == 'sps':
            n_batches_per_epoch = 120
            self.opt = sps.Sps(self.net.parameters(), n_batches_per_epoch=n_batches_per_epoch, c=0.5, adapt_flag='smooth_iter', eps=0, eta_max=None)
        else:
            self.opt = optim.SGD(self.net.parameters(), 
                                lr=self.opt_dict['lr'], 
                                momentum=self.opt_dict['momentum'], 
                                weight_decay=self.opt_dict['weight_decay'])

        # variables
        self.device = device

    def get_state_dict(self):
        state_dict = {'net': self.net.state_dict(),
                      'opt': self.opt.state_dict(),
                      }

        return state_dict

    def load_state_dict(self, state_dict):
        self.net.load_state_dict(state_dict['net'])
        self.opt.load_state_dict(state_dict['opt'])

    def on_trainloader_start(self, epoch):
        if self.opt_dict['sched']:
            ut.adjust_learning_rate_netC(self.opt, epoch, self.lr_init, self.model_dict['name'], self.dataset.name)

    def train_on_batch(self, batch):
        images, labels = batch['images'].to(self.device, non_blocking=True), batch['labels'].to(self.device, non_blocking=True)   
     
        logits = self.net(images)
        loss = F.cross_entropy(logits, labels, reduction="mean")

        self.opt.zero_grad()
        loss.backward()  

        if self.opt_dict['name'] == 'sps':
            self.opt.step(loss=loss)
        else:
            self.opt.step()
        # print(ut.compute_parameter_sum(self))

        return loss.item()
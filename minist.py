import argparse
import os
import logging
import random
import shutil
import numpy as np
from distutils.version import LooseVersion

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torch.backends.cudnn as cudnn
from torchvision import datasets, transforms
from utils.util import set_logging
from nets.simpleNet import Net
# Training settings
parser = argparse.ArgumentParser(description='PyTorch MNIST Example')
parser.add_argument('--base_dir', type=str, default='res-train-minist',
                    help='location of the log path')
parser.add_argument('--batch_size', type=int, default=512, metavar='N',
                    help='input batch size for training (default: 64)')
parser.add_argument('--test_batch_size', type=int, default=150, metavar='N',
                    help='input batch size for testing (default: 1000)')
parser.add_argument('--epochs', type=int, default=10, metavar='N',
                    help='number of epochs to train (default: 10)')
parser.add_argument('--lr', type=float, default=0.01, metavar='LR',
                    help='learning rate (default: 0.01)')
parser.add_argument('--momentum', type=float, default=0.5, metavar='M',
                    help='SGD momentum (default: 0.5)')
parser.add_argument('--seed', type=int, default=42, metavar='S',
                    help='random seed (default: 42)')
parser.add_argument('--log_interval', type=int, default=10, metavar='N',
                    help='how many batches to wait before logging training status')
parser.add_argument('--use_mixed_precision', action='store_true', default=True,
                    help='use mixed precision for training')
parser.add_argument('--data_dir', type=str, default='./data',
                    help='location of the training dataset in the local filesystem (will be downloaded if needed)')


def main(args):
    seed = args.seed
    set_random_seed(seed)
    logging.info(f'set random seed: {seed}')
    if (args.use_mixed_precision and LooseVersion(torch.__version__)
            < LooseVersion('1.6.0')):
        raise ValueError("""Mixed precision is using torch.cuda.amp.autocast(),
                            which requires torch >= 1.6.0""")

    data_dir = args.data_dir
    train_dataset = \
        datasets.MNIST(data_dir, train=True, download=True,
                        transform=transforms.Compose([
                            transforms.ToTensor(),
                            transforms.Normalize((0.1307,), (0.3081,))
                        ]))

    def worker_init_fn(worker_id):#????????????worker???????????????seed
        set_random_seed(seed + worker_id)

    train_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=16, pin_memory=True, drop_last=True, worker_init_fn=worker_init_fn)

    test_dataset = \
        datasets.MNIST(data_dir, train=False, transform=transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0.1307,), (0.3081,))
        ]))

    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=args.test_batch_size, shuffle=False, num_workers=16, pin_memory=True)

    model = Net()
    # model = nn.DataParallel(model)
    # Move model to GPU.
    model.to(device=args.device)

    optimizer = optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum)

    if args.use_mixed_precision:
        # Initialize scaler in global scale
        scaler = torch.cuda.amp.GradScaler()

    for epoch in range(1, args.epochs + 1):
        if args.use_mixed_precision:
            train_mixed_precision(epoch, scaler, model, optimizer, train_loader, train_dataset)
        else:
            train_epoch(epoch, model, optimizer, train_loader, train_dataset)
        # Keep test in full precision since computation is relatively light.
        test_acc = test(model, test_loader, test_dataset)

def train_mixed_precision(epoch, scaler, model, optimizer, train_loader, train_dataset):
    model.train()
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.cuda(), target.cuda()
        optimizer.zero_grad()
        with torch.cuda.amp.autocast():
            output = model(data)
            loss = F.nll_loss(output, target)

        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

        if batch_idx % args.log_interval == 0:
            logging.info('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}\tLoss Scale: {}'.format(
                epoch, batch_idx * len(data), len(train_dataset),
                        100. * batch_idx / len(train_loader), loss.item(), scaler.get_scale()))

def train_epoch(epoch, model, optimizer, train_loader, train_dataset):
    model.train()
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.cuda(), target.cuda()
        optimizer.zero_grad()
        output = model(data)
        loss = F.nll_loss(output, target)
        loss.backward()
        optimizer.step()
        if batch_idx % args.log_interval == 0:
            logging.info('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, batch_idx * len(data), len(train_dataset),
                        100. * batch_idx / len(train_loader), loss.item()))

def test(model, test_loader, test_dataset):
    model.eval()
    test_loss = 0.
    test_accuracy = 0.
    for data, target in test_loader:
        data, target = data.cuda(), target.cuda()
        output = model(data)
        # sum up batch loss
        test_loss += F.nll_loss(output, target, size_average=False).item()
        # get the index of the max log-probability
        pred = output.data.max(1, keepdim=True)[1]
        test_accuracy += pred.eq(target.data.view_as(pred)).cpu().float().sum()

    test_loss /= len(test_dataset)
    test_accuracy /= len(test_dataset)
    test_accuracy = test_accuracy.item()
    logging.info('\nTest set: Average loss: {:.4f}, Accuracy: {:.2f}%\n'.format(
        test_loss, 100. * test_accuracy))

    return test_accuracy

def set_random_seed(seed_num):
    cudnn.benchmark = False      #False??????????????????????????????????????????CUDNN??????
    cudnn.deterministic = True   #True ??????????????????CuDNN???????????????????????????CUDNN??????
    random.seed(seed_num)     #???python??????????????????
    np.random.seed(seed_num)  #???numpy??????????????????
    torch.manual_seed(seed_num) # ???CPU??????????????????
    torch.cuda.manual_seed(seed_num) # ?????????GPU?????????????????? torch.cuda.manual_seed_all(seed)   # ?????????GPU??????????????????

def backup_code(base_dir):
    ###????????????train???????????????dataset????????????
    code_path = os.path.join(base_dir, 'code') 
    if not os.path.exists(code_path):
        os.makedirs(code_path)
    train_name = os.path.basename(__file__)
    net_name = 'simpleNet.py'
    shutil.copy('nets/' + net_name, code_path + '/' + net_name)
    shutil.copy(train_name, code_path + '/' + train_name)

if __name__ == '__main__':
    args = parser.parse_args()
    
    if not os.path.exists(args.base_dir):
        os.makedirs(args.base_dir)
    backup_code(args.base_dir)
    log_path = os.path.join(args.base_dir, 'training.log') 
    set_logging(log_path=log_path)

    """??????GPU ID"""
    gpu_list = [0] #[0,1]
    gpu_list_str = ','.join(map(str, gpu_list))
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", gpu_list_str)
    args.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logging.info(f'Using device : {args.device}\n'
                 f'\tGPU ID is [{os.environ["CUDA_VISIBLE_DEVICES"]}],using {torch.cuda.device_count()} device\n'
                 f'\tdevice name:{torch.cuda.get_device_name(0)}')

    logging.info(args)
    try:
        main(args)
    except Exception as exception:
        logging.exception(exception)
        raise
    
import argparse, os
import torch
import math
import torch.backends.cudnn as cudnn
import torch.nn as nn
import torch.optim as optim
from torch.autograd import Variable
from torch.utils.data import DataLoader
from model.SrSENet import Net, L1_Charbonnier_loss
from data import DatasetFromHdf5
from utils import save_checkpoint
from tensorboardX import SummaryWriter

# Training settings
parser = argparse.ArgumentParser(description="PyTorch SrSENet")
parser.add_argument("--use_se", action="store_true", help="Use SELayer?")
parser.add_argument("--batchSize", type=int, default=64, help="training batch size")
parser.add_argument("--rate", default=2, type=int, help="upscale rate, Default: n=2")
parser.add_argument("--blocks", default=8, type=int, help="blocks nums of SrSEBlock, Default: n=8")
parser.add_argument("--nEpochs", type=int, default=300, help="number of epochs to train for")
parser.add_argument("--lr", type=float, default=1e-4, help="Learning Rate. Default=1e-4")
parser.add_argument("--step", type=int, default=100,
                    help="Sets the learning rate to the initial LR decayed by momentum every n epochs, Default: n=100")
parser.add_argument("--cuda", action="store_true", help="Use cuda?")
parser.add_argument("--gpus", type=int, default=4, help="nums of gpu to use")
parser.add_argument("--resume", default="", type=str, help="Path to checkpoint (default: none)")
parser.add_argument("--start-epoch", default=1, type=int, help="Manual epoch number (useful on restarts)")
parser.add_argument("--threads", type=int, default=1, help="Number of threads for data loader to use, Default: 1")
parser.add_argument("--momentum", default=0.9, type=float, help="Momentum, Default: 0.9")
parser.add_argument("--weight-decay", "--wd", default=1e-4, type=float, help="weight decay, Default: 1e-4")
parser.add_argument("--pretrained", default="", type=str, help="path to pretrained model (default: none)")
parser.add_argument("--datasets", default="", type=str, help="path to load train datasets(default: none)")


def main():
    global opt, logger
    opt = parser.parse_args()
    print(opt)

    logger = SummaryWriter()

    cuda = opt.cuda
    if cuda and not torch.cuda.is_available():
        raise Exception("No GPU found, please run without --cuda")

    seed = 774
    torch.manual_seed(seed)
    if cuda:
        torch.cuda.manual_seed(seed)

    cudnn.benchmark = True

    print("===> Loading datasets")
    train_set = DatasetFromHdf5(opt.datasets)
    training_data_loader = DataLoader(dataset=train_set, num_workers=opt.threads, batch_size=opt.batchSize,
                                      shuffle=True)

    print("===> Building model")
    model = Net(opt.blocks, opt.rate, opt.use_se)
    criterion = L1_Charbonnier_loss()

    # optionally resume from a checkpoint
    if opt.resume:
        if os.path.isfile(opt.resume):
            print("=> loading checkpoint '{}'".format(opt.resume))
            checkpoint = torch.load(opt.resume)
            opt.start_epoch = checkpoint["epoch"] + 1
            model.load_state_dict(checkpoint["state_dict"])
        else:
            print("=> no checkpoint found at '{}'".format(opt.resume))

    # optionally copy weights from a checkpoint
    if opt.pretrained:
        if os.path.isfile(opt.pretrained):
            print("=> loading model '{}'".format(opt.pretrained))
            weights = torch.load(opt.pretrained)
            model.load_state_dict(weights['state_dict'].state_dict())
        else:
            print("=> no model found at '{}'".format(opt.pretrained))

    print("===> Setting GPU")
    if cuda:
        model = nn.DataParallel(model, device_ids=[i for i in range(opt.gpus)]).cuda()
        criterion = criterion.cuda()
    else:
        model = model.cpu()
        criterion = criterion.cpu()

    print("===> Setting Optimizer")
    optimizer = optim.Adam(model.parameters(), lr=opt.lr)

    print("===> Training")
    for epoch in range(opt.start_epoch, opt.nEpochs + 1):
        train(training_data_loader, optimizer, model, criterion, epoch)


def train(training_data_loader, optimizer, model, criterion, epoch):
    print("epoch =", epoch, "lr =", optimizer.param_groups[0]["lr"])

    model.train()

    for iteration, batch in enumerate(training_data_loader, 1):

        input, label = \
            Variable(batch[0]), \
            Variable(batch[int(math.sqrt(opt.rate))], requires_grad=False)

        if opt.cuda:
            input = input.cuda()
            label = label.cuda()
        else:
            input = input.cpu()
            label = label.cpu()

        sr = model(input)
        loss = criterion(label, sr)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        if iteration % 10 == 0:
            print("===> Epoch[{}]({}/{}): Loss: {:.6f}".format(epoch, iteration, len(training_data_loader),
                                                               loss.data[0]))
            logger.add_scalar('loss', loss.data[0], len(training_data_loader) * epoch + iteration)

    save_checkpoint(model, opt.rate, epoch)


if __name__ == "__main__":
    os.system('clear')
    main()

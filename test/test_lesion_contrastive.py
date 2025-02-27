import torch
import numpy as np
import glob, os, sys
import tifffile as tiff
import numpy as np
from sklearn.manifold import TSNE
import matplotlib.pyplot as plt
from utils.data_utils import imagesc
import umap
reducer = umap.UMAP()
from os import path
import sys

#sys.path.append(path.abspath('../WorkingGan'))
import torch.nn as nn
from sklearn.neighbors import KNeighborsClassifier


def get_tiff_stack(x):
    x = x / x.max()
    if nm11:
        x = (x - 0.5) * 2
    x = torch.from_numpy(x).unsqueeze(1).float().cuda()
    return x


# get images and segmentation
def get_images_and_seg(list_img):
    x0 = get_tiff_stack(np.stack([tiff.imread(la[x]) for x in list_img], 0))
    x1 = get_tiff_stack(np.stack([tiff.imread(la[x].replace('/a/', '/b/')) for x in list_img], 0))
    seg0 = np.stack([tiff.imread(la[x].replace('/a/', '/seg/aseg/')) for x in list_img], 0)
    eff0 = np.stack([tiff.imread(la[x].replace('/a/', '/seg/aeff/')) for x in list_img], 0)
    seg1 = np.stack([tiff.imread(la[x].replace('/a/', '/seg/bseg/')) for x in list_img], 0)
    eff1 = np.stack([tiff.imread(la[x].replace('/a/', '/seg/beff/')) for x in list_img], 0)
    return x0, x1, seg0, eff0, seg1, eff1


def get_seg(x):
    # get segmentation, but apply maxpooling (8 * ratio) to match the size of the feature map
    x = torch.from_numpy(x)
    x = nn.MaxPool2d(8 * ratio)(x / 1)
    x = x.permute(1, 2, 0).reshape(-1)
    return x


def get_model(option='new'):
    if option == 'new':
        #model = torch.load('/media/ExtHDD01/logs/womac4/0719/alpha0_cutGB_vgg10_nce1/checkpoints/net_g_model_epoch_120.pth',
        #                   map_location=torch.device('cpu')).cuda()
        model = torch.load(
            '/media/ExtHDD01/logs/womac4/mlp/alpha0_cutGB2_vgg0_nce4_0001/checkpoints/net_g_model_epoch_120.pth',
            map_location=torch.device('cpu')).cuda()

    elif option == 'old':
        model = torch.load('/media/ExtHDD01/logs/womac4/3D/test4fixmcVgg10/checkpoints/net_g_model_epoch_40.pth',
                           map_location=torch.device('cpu')).cuda(); nomask = False; nm11 = False;
    return model


def pain_significance_monte_carlo(x0, x1, model, skip=1, nomask=False):
    # pain significance
    outall = []
    print('running monte carlo.....')
    for mc in range(100):
        if nomask:
            try:
                o = model(x0, alpha=skip)['out0'][:, 0, :, :].detach().cpu()
            except:
                o = model(x0, a=1)['out0'][:, 0, :, :].detach().cpu()
        else:
            try:
                o = model(x0, alpha=1, method='encode')
                o = model(o, alpha=1, method='decode')['out0'].detach().cpu()
            except:
                o = model(x0, a=1)['out0'].detach().cpu()
            o = nn.Sigmoid()(o)
            o = torch.multiply(o[:, 0, :, :], x0[:, 0, :, :].cpu())
        outall.append(o)
    print('done running monte carlo.....')

    outall = [x0[:, 0, :, :].cpu() - x for x in outall]

    mean = torch.mean(torch.stack(outall, 3), 3)
    var = torch.var(torch.stack(outall, 3), 3)
    sig = torch.divide(mean, torch.sqrt(var) + 0.01)
    return mean, var, sig

###
# Prepare data and model
###
# get the model
model = get_model()

nomask = False
nm11 = False
ratio = 1  # the
skip = 1
fWhich = [0, 0, 0, 1]  # which layers of features to use

root = '/media/ExtHDD01/Dataset/paired_images/womac4/full/'
# list of images
la = sorted(glob.glob(root + 'a/*'))

# list of images to be tested
list_img = [41, 534, 696, 800, 827, 1180, 1224, 1290, 6910, 9256]
list_img = [x - 1 for x in list_img]  # -1 because its 1-indexed

# name of the images
name = [la[y].split('/')[-1] for y in list_img]

# load images and segmentations
x0, x1, seg0, eff0, seg1, eff1 = get_images_and_seg(list_img=list_img)
(seg0, eff0, seg1, eff1) = [get_seg(x) for x in (seg0, eff0, seg1, eff1)]

###
# get pain significance by monte carlo
###

mean, var, sig = pain_significance_monte_carlo(x0, x1, model, skip=skip, nomask=nomask)

# collect features
f0 = model(x0, method='encode')
f1 = model(x1, method='encode')

f0 = [nn.MaxPool2d(ratio * j)(i) for (i, j) in zip(f0, [8, 4, 2, 1])]
f1 = [nn.MaxPool2d(ratio * j)(i) for (i, j) in zip(f1, [8, 4, 2, 1])]

#f0 = f0[-1:]
#f1 = f1[-1:]

f0 = torch.cat(f0, 1)
f1 = torch.cat(f1, 1)
C = f0.shape[1]
f0 = f0.permute(1, 2, 3, 0).reshape(C, -1).cpu().detach().numpy()
f1 = f1.permute(1, 2, 3, 0).reshape(C, -1).cpu().detach().numpy()

# features
# data = f0[-1].permute(1, 2, 3, 0).reshape(256, -1).cpu().detach().numpy()
# e0 = tsne.fit_transform(data.T)

# lesion
lesion = nn.MaxPool2d(8 * ratio)(sig)
lesion = lesion.permute(1, 2, 0).reshape(-1)

# double everything
lesion = np.concatenate([lesion, lesion * 0], 0)
seg = np.concatenate([seg0, seg1], 0)
eff = np.concatenate([eff0, eff1], 0)

# features
data = np.concatenate([f0, f1], 1)
import time

tini = time.time()
e = reducer.fit_transform(data.T)   # umap
print('umap time used: ' + str(time.time() - tini))
e[:, 0] = (e[:, 0] - e[:, 0].min()) / (e[:, 0].max() - e[:, 0].min())
e[:, 1] = (e[:, 1] - e[:, 1].min()) / (e[:, 1].max() - e[:, 1].min())

# pain
pain = np.concatenate([np.ones((f0.shape[1])), 2 * np.ones((f1.shape[1]))])
P = 1

for condition in [0, 1, 2]:
    le = (lesion >= 0) / 1
    plt.scatter(e[le == 1, 0], e[le == 1, 1], s=0.05 * np.ones(((le == 1).sum(), 1))[:, 0])
    for trd in [4, 6, 8]:
        if condition == 0:
            le = (lesion >= trd) & (seg > 0) & (pain == P)
        if condition == 1:
            le = (lesion >= trd) & (eff == 1) & (pain == P)
        if condition == 2:
            le = (lesion >= trd) & (eff == 0) & (seg == 0) & (pain == P)

        plt.scatter(e[le == 1, 0], e[le == 1, 1], s=2 * np.ones(((le == 1).sum(), 1))[:, 0])
    plt.xlim(0, 1)
    plt.ylim(0, 1)
    plt.show()

label = -10 * np.ones((e.shape[0]))

#label[lesion >= 8] = 1
# label[lesion < 4] = 0

label[(lesion >= 6) & (seg > 0)] = 1
label[(lesion >= 6) & (eff > 0)] = 1
# label[lesion < 2] = 0
label[(pain == 2)] = 0

# knn
knn = KNeighborsClassifier(n_neighbors=10)
knn.fit(e[label >= 0, :], label[label >= 0])

fout = knn.predict(e)
fout[label >= 0] = label[label >= 0]

plt.scatter(e[fout == 0, 0], e[fout == 0, 1], s=0.05 * np.ones(((fout == 0).sum(), 1))[:, 0])
plt.scatter(e[fout == 1, 0], e[fout == 1, 1], s=2 * np.ones(((fout == 1).sum(), 1))[:, 0])
plt.show()

# resize back to pixel space
fout = fout[:fout.shape[0] // 2]
fout = fout.reshape((48 // ratio, 48 // ratio, len(list_img)))
fout = torch.from_numpy(fout).permute(2, 0, 1).unsqueeze(1)

for folder_name in ['fmap', 'ori', 'sig', 'mean', 'eff', 'seg']:
    os.makedirs('output/' + folder_name, exist_ok=True)

x0, x1, seg0, eff0, seg1, eff1 = get_images_and_seg(list_img=list_img)
for i in range(len(list_img)):
    tiff.imwrite('output/ori/' + name[i], x0[i, 0, :, :].cpu().numpy())
    tiff.imwrite('output/seg/' + name[i], seg0[i, :, :])
    tiff.imwrite('output/eff/' + name[i], eff0[i, :, :])
    tiff.imwrite('output/fmap/' + name[i], fout[i, 0, :, :].numpy())
    tiff.imwrite('output/sig/' + name[i], sig[i, :, :].cpu().numpy())
    tiff.imwrite('output/mean/' + name[i], mean[i, :, :].cpu().numpy())

fout = nn.Upsample(scale_factor=8 * ratio, mode='bilinear')(fout)
fout[fout <= 0] = 0

# sig = torch.from_numpy(tiff.imread('sigold.tif'))
fout = torch.multiply(fout[:, 0, :, :], sig).numpy()

tiff.imwrite('output/fout.tif', np.concatenate([fout, sig.numpy()], 2))

# pain-no pain comparison
# plt.scatter(e[:e.shape[0] // 2, 0], e[:e.shape[0] // 2, 1], s=0.05 * np.ones(e.shape[0] // 2))
# plt.scatter(e[e.shape[0] // 2:, 0], e[e.shape[0] // 2:, 1], s=0.01 * np.ones(e.shape[0] // 2))
# plt.show()
#!/usr/bin/python
# -*- coding: utf-8 -*-

import torch
from torch import nn
import torch.nn.functional as F
from tensorboardX import SummaryWriter


def CarteActivation(self, input, output):
    # input is a tuple of packed inputs
    # output is a Tensor. output.data is the Tensor we are interested
    print('Inside ' + self.__class__.__name__ + ' forward')
    print('')
    print('input: ', type(input))
    print('input[0]: ', type(input[0]))
    print('output: ', type(output))
    print('')
    print('input size:', input[0].size())
    print('output size:', output.data.size())
    print('output norm:', output.data.norm())

    # writer = SummaryWriter('../../output/runs/carteActivation')
    # writer.close()



class UNet(nn.Module):
    def __init__(self, in_channels=1, n_classes=2, depth=5, wf=6, padding=False,
                 batch_norm=False, up_mode='upconv'):
        """
        Implementation of
        U-Net: Convolutional Networks for Biomedical Image Segmentation
        (Ronneberger et al., 2015)
        https://arxiv.org/abs/1505.04597

        Using the default arguments will yield the exact version used
        in the original paper

        Args:
            in_channels (int): number of input channels
            n_classes (int): number of output channels
            depth (int): depth of the network
            wf (int): number of filters in the first layer is 2**wf
            padding (bool): if True, apply padding such that the input shape
                            is the same as the output.
                            This may introduce artifacts
            batch_norm (bool): Use BatchNorm after layers with an
                               activation function
            up_mode (str): one of 'upconv' or 'upsample'.
                           'upconv' will use transposed convolutions for
                           learned upsampling.
                           'upsample' will use bilinear upsampling.
        """
        super(UNet, self).__init__()
        assert up_mode in ('upconv', 'upsample')
        self.padding = padding
        self.depth = depth
        prev_channels = in_channels
        self.down_path = nn.ModuleList() # vide
        for i in range(depth):
            self.down_path.append(UNetConvBlock(prev_channels, 2**(wf+i), padding, batch_norm))
            prev_channels = 2**(wf+i)

        self.up_path = nn.ModuleList()
        for i in reversed(range(depth - 1)):
            self.up_path.append(UNetUpBlock(prev_channels, 2**(wf+i), up_mode, padding, batch_norm))
            prev_channels = 2**(wf+i)

        self.last = nn.Conv2d(prev_channels, n_classes, kernel_size=1)

        if (False):
            ### Fichier permettant de vérifier la structure du réseau
            # Attention les doublons, les maxpool ne sont pas affichés --> lire la doc
            f=open("output/logBlocs.txt","w")
            f.write("Paramètres du réseau\n\n")
            f.write("in_channels : "+str(in_channels)+"\n")
            f.write("n_classes : "+str(n_classes)+"\n")
            f.write("Depth : "+str(depth)+"\n")
            f.write("Padding : "+str(padding)+"\n")
            f.write("Wf : "+str(wf)+"\n")
            f.write("batch_norm : "+str(batch_norm)+"\n")
            f.write("up_mode : "+str(up_mode)+"\n")


            f.write("\nDescente :\n")
            for id, m in enumerate(self.down_path):
                f.write(str(id+1)+" --> "+str(m)+"\n")

            f.write("\nRemontée :\n")
            for id, m in enumerate(self.up_path):
                f.write(str(id+1)+" --> "+str(m)+"\n")

            f.write("\nDernière couche :\n")
            f.write(str(self.last))
            f.close()
            ###

    def forward(self, x):
        blocks = []
        for i, down in enumerate(self.down_path):
            x = down(x)
            down.register_forward_hook(CarteActivation)
            if i != len(self.down_path)-1:
                blocks.append(x) # Sauvegarde du "bridge" "copy and crop"
                x = F.avg_pool2d(x, 2)

        for i, up in enumerate(self.up_path):
            x = up(x, blocks[-i-1]) # On rappelle l'image obtenue à la descente

        return self.last(x)


class UNetConvBlock(nn.Module):
    def __init__(self, in_size, out_size, padding, batch_norm):
        super(UNetConvBlock, self).__init__()
        block = []

        block.append(nn.Conv2d(in_size, out_size, kernel_size=3,
                               padding=int(padding)))
        block.append(nn.ReLU())
        if batch_norm:
            block.append(nn.BatchNorm2d(out_size))

        block.append(nn.Conv2d(out_size, out_size, kernel_size=3,
                               padding=int(padding)))
        block.append(nn.ReLU())
        if batch_norm:
            block.append(nn.BatchNorm2d(out_size))

        # block.append(nn.Sigmoid())

        self.block = nn.Sequential(*block)

    def forward(self, x):
        out = self.block(x)
        return out


class UNetUpBlock(nn.Module):
    def __init__(self, in_size, out_size, up_mode, padding, batch_norm):
        super(UNetUpBlock, self).__init__()
        if up_mode == 'upconv':
            self.up = nn.ConvTranspose2d(in_size, out_size, kernel_size=2, stride=2)
        elif up_mode == 'upsample':
            self.up = nn.Sequential(nn.Upsample(mode='bilinear', scale_factor=2), nn.Conv2d(in_size, out_size, kernel_size=1))

        self.conv_block = UNetConvBlock(in_size, out_size, padding, batch_norm)

    def center_crop(self, layer, target_size):
        # Rétrécie l'image en enlevant des pixels sur les bords
        _, _, layer_height, layer_width = layer.size()
        diff_y = (layer_height - target_size[0]) // 2
        diff_x = (layer_width - target_size[1]) // 2
        return layer[:, :, diff_y:(diff_y + target_size[0]), diff_x:(diff_x + target_size[1])]

    def forward(self, x, bridge):
        up = self.up(x)
        crop1 = self.center_crop(bridge, up.shape[2:]) # crop1.shape = [N, C, H, W]
        # Concaténation suivant la direction 1 :
        # on rajoute 1 channel correspondant à l'image telle qu'elle était lors de la descente
        out = torch.cat([up, crop1], 1)

        out = self.conv_block(out)

        return out
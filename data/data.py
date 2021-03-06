import json
from pathlib import Path

import numpy as np
from tqdm import tqdm
import soundfile as sf

import torch as th
from torch.utils import data

train_path = Path("/home/machao/multi_task_conv_tasnet_whamr/data/clean_8k_json/train_load.json")
valid_path = Path("/home/machao/multi_task_conv_tasnet_whamr/data/clean_8k_json/valid_load.json")
train_data = {
    "json_path": train_path,
    "split_len": 32000,
}
valid_data = {
    "json_path": valid_path,
    "split_len": 32000,
}


def all_loaders_in_one(batch_size,
                       num_workers=4,
                       pin_memory=True):
    train_dataset = dataset(**train_data)
    valid_dataset = dataset(**valid_data)
    train_data_loader = data.DataLoader(dataset=train_dataset,
                                        batch_size=batch_size,
                                        collate_fn=train_dataset.collate,
                                        shuffle=True,
                                        num_workers=num_workers,
                                        pin_memory=pin_memory)
    valid_data_loader = data.DataLoader(dataset=valid_dataset,
                                        batch_size=batch_size,
                                        collate_fn=valid_dataset.collate,
                                        shuffle=False,
                                        num_workers=num_workers,
                                        pin_memory=pin_memory)
    return train_data_loader, valid_data_loader


class dataset(data.Dataset):

    def __init__(self, json_path, split_len=32000):
        self.database = []
        self.split_len = split_len
        print(f"loading data from {json_path}")
        with open(json_path, "r") as f:
            path_list = json.load(f)
        for tmp_dict in tqdm(path_list):
            tmp_data = self.load_one_data(tmp_dict)
            self.database.append(tmp_data)

    def load_one_data(self, tmp_dict):
        start = tmp_dict["start"]
        end = tmp_dict["end"]
        assert (end - start) == self.split_len

        s1path = tmp_dict["path_s1"]
        s2path = tmp_dict["path_s2"]
        s1rpath = tmp_dict["path_s1_r"]
        s2rpath = tmp_dict["path_s2_r"]
        mixpath = tmp_dict["path_mix"]
        mixapath = tmp_dict["path_mix_a"]

        s1, _ = sf.read(s1path)
        s1 = s1.astype(np.float32)
        s2, _ = sf.read(s2path)
        s2 = s2.astype(np.float32)
        s1_r, _ = sf.read(s1rpath)
        s1_r = s1_r.astype(np.float32)
        s2_r, _ = sf.read(s2rpath)
        s2_r = s2_r.astype(np.float32)
        mix, _ = sf.read(mixpath)
        mix = mix.astype(np.float32)
        mix_a, _ = sf.read(mixapath)
        mix_a = mix_a.astype(np.float32)
        return (mix[start:end], mix_a[start:end], s1[start:end], s2[start:end], s1_r[start:end], s2_r[start:end])
    
    def __len__(self):
        return len(self.database)

    def __getitem__(self, idx):
        return self.database[idx]
    
    def collate(self, inputs):
        mixs, mixas, s1s, s2s, s1rs, s2rs = zip(*inputs)
        mixs = th.from_numpy(np.asarray(mixs)).type(th.FloatTensor)
        mixas = th.from_numpy(np.asarray(mixas)).type(th.FloatTensor)
        s1s = th.from_numpy(np.asarray(s1s)).type(th.FloatTensor)
        s2s = th.from_numpy(np.asarray(s2s)).type(th.FloatTensor)
        s1rs = th.from_numpy(np.asarray(s1rs)).type(th.FloatTensor)
        s2rs = th.from_numpy(np.asarray(s2rs)).type(th.FloatTensor)
        refs = th.stack([s1s, s2s], dim=1)
        refrs = th.stack([s1rs, s2rs], dim=1)
        batch = [mixs, mixas, refs, refrs]
        return batch


if __name__ == "__main__":
    # train_dataset = dataset(**train_data)
    valid_dataset = dataset(**valid_data)
    mix, mixa, s1, s2, s1r, s2r = valid_dataset[5000]
    # np.set_printoptions(threshold=np.inf)
    # print(mix)
    # print(s1)
    print(type(mix))
    print(type(s1))
    print(np.shape(mix))
    print(np.shape(mixa))
    print(np.shape(s1))
    batch_size = 4
    valid_data_loader = data.DataLoader(dataset=valid_dataset,
                                        batch_size=batch_size,
                                        collate_fn=valid_dataset.collate,
                                        shuffle=False)
    for utt, egs in enumerate(valid_data_loader):
        mixs, mixas, refs, refrs = egs
        if utt == 100:
            print(mixas.size())
            print(refs.size())
            break

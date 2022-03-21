import argparse
import json
import os
import time
from pathlib import Path

import torch
import torch.optim as optim
from data.data import all_loaders_in_one
# import network
from nnet.original_conv_tasnet import model_info
from nnet.original_conv_tasnet import TasNet as nnet
from nnet.losses import batch_log_mse_torch, loss_calc
from torch.optim.lr_scheduler import ExponentialLR

# date_str = time.strftime("%m%d", time.localtime())
model_name = model_info["model_name"]
loss_type = model_info["loss_type"]
exp_name = "teacher"
exp_path = Path("/data/machao/multi_task_conv_tasnet_whamr/exp/") / exp_name

parser = argparse.ArgumentParser()
parser.add_argument('--batch_size', default=4, type=int, help='train batch size per gpu')
parser.add_argument('--num_epochs', default=100, type=int, help='train epochs number')
parser.add_argument('--exp', default=exp_path, type=Path, help='exp name')
parser.add_argument('--gpus', default="0,1,2,3,4,5,6,7", type=str, help="gpu ids")
args = parser.parse_args()


def log_str(strs, log_path):
    with open(log_path, "a") as f:
        f.write(strs + "\n")
    print(strs)


def main():
    if not os.path.isdir(args.exp):
        os.makedirs(args.exp)

    log_path = args.exp / "log.txt"
    with open(log_path, "w") as f:
        f.write(f"exp name: {exp_name}" + "\n")
    print(f"exp name: {exp_name}")

    model_json_path = args.exp / "model_info.json"
    with open(model_json_path, "w") as f:
        json.dump(model_info, f, indent=4)

    gpuids = tuple(map(int, args.gpus.split(",")))
    n_gpu = len(gpuids)
    log_str(f"gpu numbers: {n_gpu}", log_path)
    model = nnet(model_info)
    # TODO - check exists
    #  cpt = torch.load('./best.pth.tar')
    #  net.load_state_dict(cpt["model_state_dict"])
    # cpt = torch.load("/data/machao/multi_task_conv_tasnet_whamr/exp/conv-tasnet_whamr_sisdr_1_1_unshared_stack_.5_.5_0/best.pth.tar")
    # model.load_state_dict(cpt["model_state_dict"])
    model.to(torch.device('cuda', 0))

    num_params = sum([param.nelement() for param in model.parameters()]) / 10.0**6
    log_str("model params numbers: {:.2f}M".format(num_params), log_path)

    all_batch_size = args.batch_size * n_gpu
    train_data_loader, valid_data_loader = all_loaders_in_one(all_batch_size)

    torch.set_printoptions(precision=10, profile="full")

    # Optimizer
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    # Learning rate scheduler
    scheduler = ExponentialLR(optimizer, gamma=0.98)

    best_loss = 1e10
    early_stop = 0
    disp_freq = 100

    for epoch in range(args.num_epochs):

        log_str('-' * 42, log_path)
        tic = time.time()
        log_str("epoch {} training start!".format(epoch + 1), log_path)
        cur_lr = optimizer.param_groups[0]["lr"]
        log_str("lr = {:.3e}".format(cur_lr), log_path)

        model.train()
        train_loss = 0
        for utt, egs in enumerate(train_data_loader):
            egs = list(map(lambda x: x.to(torch.device('cuda', 0)), egs))
            train_mix, train_mix_a, train_clean, train_clean_reverb = egs

            train_est, feature = torch.nn.parallel.data_parallel(model, (train_mix_a),
                                                        device_ids=gpuids)

            batch_loss = loss_calc(train_est, train_clean, model_info['loss_type'])

            loss = torch.mean(batch_loss)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            train_loss += loss.item()
            if (utt + 1) % disp_freq == 0:
                log_str("utt {}, train loss: {:.4f}".format(utt + 1, train_loss / (utt + 1)), log_path)
        train_len = utt + 1

        model.eval()
        log_str("epoch {} validation start!".format(epoch + 1), log_path)
        valid_loss = 0
        print_loss = 0
        with torch.no_grad():
            for utt, egs in enumerate(valid_data_loader):
                egs = list(map(lambda x: x.to(torch.device('cuda', 0)), egs))
                valid_mix, valid_mix_a, valid_clean, valid_clean_reverb = egs

                valid_est, feature = torch.nn.parallel.data_parallel(model, (valid_mix_a),
                                                            device_ids=gpuids)

                batch_loss = loss_calc(valid_est, valid_clean, model_info['loss_type'])
                loss = torch.mean(batch_loss)

                valid_loss += loss.item()
                print_loss += loss.item()
                if (utt + 1) % disp_freq == 0:
                    log_str("utt {}, valid loss: {:.4f}, anechoic sisdr: {:.4f}".format(utt + 1, valid_loss / (utt + 1), print_loss / (utt + 1)), log_path)
        valid_len = utt + 1

        tr_loss = train_loss / train_len
        cv_loss = valid_loss / valid_len
        pr_loss = print_loss / valid_len

        cpt = {
            "epoch": epoch + 1,
            "model_info": model_info,
            "model_state_dict": model.state_dict(),
            "optim_state_dict": optimizer.state_dict()
        }
        if cv_loss < best_loss:
            early_stop = 0
            best_loss = cv_loss
            torch.save(cpt, args.exp / 'best.pth.tar')
        else:
            early_stop += 1
        torch.save(cpt, args.exp / 'last.pth.tar')
        log_str("epoch {} summary: train loss: {:.4f}, valid loss: {:.4f}, anechoic sisdr: {:.4f}".format(epoch + 1, tr_loss, cv_loss, pr_loss), log_path)
        toc = time.time()
        log_str("epoch {} cost {:.4f} mins".format(epoch + 1, (toc - tic) / 60), log_path)
        if early_stop > 0:
            log_str("cv_loss has gone up for {} epoch(s)".format(early_stop), log_path)
        if early_stop > 10:
            print(time.strftime("%Y-%m-%d-%H:%M:%S",time.localtime()))
            break

        scheduler.step()


if __name__ == '__main__':
    main()

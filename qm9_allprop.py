import os
from pathlib import Path
import torch
import numpy as np
from multiprocessing import Pool
from utils import read_xyz_allprop, read_xyz_ext
from scf import geom_scf_6, bi_gen_edge_feature_6
from atom_graph import calculate_Dij, gen_bonds_mini
from torch_geometric.data import Data, InMemoryDataset
from tqdm import tqdm

def mapping(mol_object):
    mat_ovlp, mat_hcore, aoslice = geom_scf_6(mol_object.atom)
    Dij = calculate_Dij(mol_object.R)
    edge_index = gen_bonds_mini(Dij, cutoff=5.0)
    assert aoslice.shape[0]==edge_index.max()+1, f'error found in idx {mol_object.idx}, the max index in graph is {edge_index.max()}'
    edge_attr = bi_gen_edge_feature_6(mat_ovlp, mat_hcore, aoslice, edge_index, mol_object.Z)

    return Data(x = mol_object.Z, edge_index = edge_index, edge_attr = edge_attr, y = mol_object.Label, edge_num = edge_index.size()[1],
                  idx = mol_object.idx, atom_pos = mol_object.R)    #is_bond = is_bond, bond_type = bond_type,

def paralle(mol_list):
    P = Pool(processes=int(os.cpu_count()))
    datas = list(tqdm(P.imap(func=mapping, iterable=mol_list)))
    P.close()
    P.join()

    return datas

class QM9_allprop(InMemoryDataset):
    def __init__(self, root = '.', input_file = './sdfs/qm9U0_std.sdf', prop_len=12, transform = None, pre_transform = None, pre_filter = None):
        self.root = Path(root)
        self.input_file = input_file
        self.prop_len = prop_len
        self.prefix = input_file.split('.')[0]
        self.suffix = input_file.split('.')[1]
        if '/' in self.input_file:
            self.prefix = self.input_file.split('/')[-1].split('.')[0]
            self.suffix = self.input_file.split('/')[-1].split('.')[1]
        super(QM9_allprop, self).__init__(root, transform=transform, pre_transform=pre_transform)
        self.data, self.slices = torch.load(self.processed_paths[0])

    @property
    def raw_file_names(self):
        return self.input_file
    
    @property
    def processed_file_names(self):
        return 'new_bi_'+ self.prefix + "_6.pt"
    
    def download(self):
        pass

    def process(self):
        assert self.suffix in ['xyz', 'extxyz'], "file type not supported"
        if self.suffix == 'xyz':
            mol_list = read_xyz_allprop(self.input_file, prop_len=self.prop_len)
        else:
            mol_list = read_xyz_ext(self.input_file, num_properties=self.prop_len)
        datas = paralle(mol_list)
        
        torch.save(self.collate(datas),self.processed_dir +'/new_bi_' + self.prefix + '_6.pt')
        print('done')
    
if __name__=='__main__':
    import datetime
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('--input_file', type=str, default='./raw/qm9_origin.xyz')
    parser.add_argument('--prop_len', type=int, default=12)
    args = parser.parse_args()
    start_time = datetime.datetime.now()

    torch.multiprocessing.set_sharing_strategy('file_system')

    import sys
    from torch.utils.data import dataloader
    from multiprocessing.reduction import ForkingPickler
 
    default_collate_func = dataloader.default_collate
 
 
    def default_collate_override(batch):
        dataloader._use_shared_memory = False
        return default_collate_func(batch)
 
    setattr(dataloader, 'default_collate', default_collate_override)
 
    for t in torch._storage_classes:
      if sys.version_info[0] == 2:
        if t in ForkingPickler.dispatch:
            del ForkingPickler.dispatch[t]
      else:
        if t in ForkingPickler._extra_reducers:
            del ForkingPickler._extra_reducers[t]
            
    dataset = QM9_allprop(input_file=f'{args.input_file}', prop_len=args.prop_len)
    end_time = datetime.datetime.now()
    print(f'time consumed: {-(start_time - end_time).total_seconds() :.2f}')

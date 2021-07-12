from pathlib import Path
from pyhdx import PeptideMasterTable, read_dynamx, HDXMeasurement
from pyhdx.fitting import fit_gibbs_global, fit_rates_weighted_average
from pyhdx.fileIO import csv_to_protein
from pyhdx.local_cluster import default_client
from pyhdx.support import pprint_df_to_file

guess = False
epochs = 1000  # For real applications used higher values, ie 100000
root_dir = Path().resolve().parent
test_data_dir = root_dir / 'tests' / 'test_data'
input_file_path = test_data_dir / 'ecSecB_apo.csv'

# Load the data of two Dynamx files, and combine the result to one table
data = read_dynamx(test_data_dir / 'ecSecB_apo.csv', test_data_dir / 'ecSecB_dimer.csv')

pmt = PeptideMasterTable(data, drop_first=1, ignore_prolines=True, remove_nan=False)
pmt.set_control(('Full deuteration control', 0.167))
temperature, pH = 273.15 + 30, 8.
hdxm = HDXMeasurement(pmt.get_state('SecB WT apo'), temperature=temperature, pH=pH)

if guess:
    client = default_client()
    wt_avg_result = fit_rates_weighted_average(hdxm, client=client)
    init_guess = wt_avg_result.output
else:
    #todo initial guesse needs to be updated
    init_guess = csv_to_protein(test_data_dir / 'ecSecB_guess.txt', header=[2], index_col=0)

gibbs_guess = hdxm.guess_deltaG(init_guess['rate'])
fr_torch = fit_gibbs_global(hdxm, gibbs_guess, epochs=epochs)
print(fr_torch.metadata['total_loss'])



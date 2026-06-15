# The files in this directory are intended for **CIE integration**.  
The results in `index.html` are pWCET values, and `sdrt_node_pwcet_table.csv` is a mapping table between CARET nodes and callback functions.  
We fill the pWCET values into this table, using **callback function latency** as a proxy for **node latency**.

Some callback functions are shared by two or more nodes.  
In those cases, we must use the methods under the `callback_to_node_latency/` folder to split the shared callback latency into **per-node latency**.  
After obtaining per-node values, we write them back into the table and finally use the completed table as input parameters for **CIE**.
import pandas as pd 
from pulp import *
from collections import defaultdict, deque
import csv
import sys


# orders = []
loc_veh_class = {}  # {'location_code':[vehicle_class]}
with open("../inputs/locations.csv",'r') as f:
    reader = csv.DictReader(f)
    headers = [header.strip() for header in reader.fieldnames]
    for row in reader:
        loc_veh_class.update({row[headers[0]]:eval(row[headers[1]])})


vehicles_dict ={}  # {'id' : ['class','max_wt','fixed cost','variable cost']}
vehicles = []        # list of unique veh_id
vehicle_class = {}   #{'class' : [veh_id]}
 
with open("../inputs/trucks.csv",'r') as f:
    reader = csv.DictReader(f)
    headers = [header.strip() for header in reader.fieldnames]
    for row in reader:
        q = int(row[headers[1]])
        vehicles_dict.update({row[headers[3]]:[row[headers[0]],q,2*q,int(20-(q/1000))]})
        vehicles.append(row[headers[3]])
        if row[headers[0]] not in vehicle_class:
            vehicle_class[row[headers[0]]] = [row[headers[3]]]
        else:
            vehicle_class[row[headers[0]]].append(row[headers[3]])

# print('Vehicles available:',len(vehicles))
# print(vehicles_dict)
# sys.exit()

demands = {}     #{order_id:location_code,demand_weight}
orders = []     #list of invoice_ordeer
with open("../inputs/order_list_14J.csv",'r') as f:
    reader = csv.DictReader(f)
    headers = [header.strip() for header in reader.fieldnames]
    for row in reader:
        orders.append(row[headers[0]])
        demands.update({row[headers[0]]:[row[headers[2]],float(row[headers[3]])]})

orders.insert(0,'INV_source_00')
# print(len(orders))
# sys.exit()
orders.append('INV_sink_00')
# print(demands)

def return_source_dest_code(invoice):
    return demands[invoice][0]

loc_vehicle_id = {}   #{'loc_code' : [veh_id]}

for id_key, vehicle_list in loc_veh_class.items():
    all_vehicle_ids = []
    for vehicle_type in vehicle_list:
        all_vehicle_ids.extend(vehicle_class.get(vehicle_type, []))
    
    loc_vehicle_id[id_key] = all_vehicle_ids

order_vehicle_id = {}    #{'invoice' : [veh_id]}
for ord in orders:
    if (ord == 'INV_source_00') or (ord == 'INV_sink_00'):
        order_vehicle_id[ord] = loc_vehicle_id['A123']
    else:
        order_vehicle_id[ord] = loc_vehicle_id[return_source_dest_code(ord)]
# print(order_vehicle_id)
# sys.exit()

class DistanceTravelTime():
    def __init__(self,source_location_code,destination_location_code,travel_distance_in_km,travel_time_in_min):
        self.source_location_code = source_location_code
        self.destination_location_code = destination_location_code
        self.travel_distance_in_km = float(travel_distance_in_km)
        self.travel_time_in_min = float(travel_time_in_min)

def read_travel_matrix(file_path):
    travel = []
    with open(file_path, mode='r') as file:
        reader = csv.DictReader(file)
        headers = [header.strip() for header in reader.fieldnames]
        for row in reader:
            dist = DistanceTravelTime(
                source_location_code=row[headers[0]],
                destination_location_code=row[headers[1]],
                travel_distance_in_km=row[headers[2]],
                travel_time_in_min =row[headers[3]]
            )
            travel.append(dist)
    return travel

travel_matrix = read_travel_matrix("../MT-CVRPTW_inputs/travel_matrix.csv")     # List of travel_matrix objects


def return_dist_time(source_code,dest_code):  # returns (dist,time)
    if source_code == 'INV_source_00':
        source_code = 'A123'
    else:
        source_code = return_source_dest_code(source_code)
    if dest_code == 'INV_sink_00':
        dest_code = 'A123'
    else:
        dest_code = return_source_dest_code(dest_code)

    for obj in travel_matrix:
        if (obj.source_location_code == source_code ) and (obj.destination_location_code == dest_code):
            return [float(obj.travel_distance_in_km),float(obj.travel_time_in_min)]    
    return [0,0]



def build_model(orders,vehicles,demands,vehicles_dict,order_vehicle_id):
    prob = LpProblem("CVRPTW", LpMinimize)
    # ****************************************
    # Defining decision variables
    # ****************************************
    x = {} #Binary x_i,j,v := 1 if vehicle v visits city j after city i; otherwise 0
    for i in orders[:-1]:
        for j in orders[1:]:
            if i!=j:
                if i == 'INV_source_00' and j == 'INV_sink_00':
                    continue
                for v in vehicles:
                    if (v in order_vehicle_id[i]) and (v in order_vehicle_id[j]):
                        x[(i,j,v)] = LpVariable('x'+'#'+ str(i) + '#' + str(j) + '#' + str(v),cat = 'Binary')
                    
    # for i in orders[:-1]:  #i!='A123'
    #     for j in orders[1:]:   #j!='source'
    #         for v in vehicles:
    #             if i != j :
    #                 x[(i,j,v)] = LpVariable('x_' + str(i) + '_' + str(j) + '_' + str(v),cat = 'Binary')
    
    print('xijv variables',len(x))
    sys.stdout.flush()
    s = {} #Continuous s_i,v : = time vehicle v starts to service customer i
    for i in orders:
        for v in vehicles:
            if i == 'INV_source_00':      #Assuming loading happens before 8 and vehicle ready to serve from 8
                s[(i,v)] = LpVariable('s#' + str(i) + '#' + str(v),lowBound=480,upBound = 1080, cat = 'Continuous')
            elif i == 'INV_sink_00':
                s[(i,v)] = LpVariable('s#' + str(i) + '#' + str(v),lowBound=480, cat = 'Continuous')
            else:
                s[(i,v)] = LpVariable('s#' + str(i) + '#' + str(v),lowBound=480,upBound = 1320, cat = 'Continuous')

    print('siv variables',len(s))
    sys.stdout.flush()

    I = {}  # I_v := 1 if vehicle v is used; otherwise 0
    for v in vehicles:
        I[v] = LpVariable('I#' + str(v) , cat = 'Binary')

    print(f'Iv variables {len(I)}')
    sys.stdout.flush()
    # ********************************************
    # Objective
    # ********************************************
    # Minimize the number of vehicles used
    if objective_1:
        print(f"Minimize the number of vehicles used")
        sys.stdout.flush()
        obj_val = 0 
        for v in vehicles:
            obj_val+=I[v]

        prob += obj_val

    # Minimize total travel distance
    if objective_2:
        print(f"Minimize total travel distance")
        sys.stdout.flush()
        obj_val = 0
        for v in vehicles:
            for i in orders[:-1]:
                for j in orders[1:]:
                    if (i,j,v) in x:
                        obj_val += (return_dist_time(i,j)[0])*x[(i,j,v)]

        prob += obj_val

    # Minimize total cost
    if objective_3:
        print(f"Minimize total cost")
        sys.stdout.flush()
        obj_val = 0
        for v in vehicles:
            obj_val+= I[v]*vehicles_dict[v][2]

        for v in vehicles:
            for i in orders[:-1]:
                for j in orders[1:]:
                    if (i,j,v) in x:
                        obj_val += (return_dist_time(i,j)[0])*x[(i,j,v)]*vehicles_dict[v][3]

        prob += obj_val
    print("Finished modelling objective")
    sys.stdout.flush()
    # ********************************************
    # Constraints
    # ********************************************
    # Start from depot
    for v in vehicles:
        prob += lpSum(x[('INV_source_00',j,v)] for j in orders[1:-1] if ('INV_source_00',j,v) in x) == I[v], f"Source[{('A123',j,v)}]"

    print("Finished modelling Start from depot")
    sys.stdout.flush()

    # End at depot
    for v in vehicles:
        prob += lpSum(x[(i,'INV_sink_00',v)] for i in orders[1:-1] if (i,'INV_sink_00',v) in x) == I[v], f"Sink[{(i,'A123',v)}]"

    print("Finished modelling End at depot")
    sys.stdout.flush()
    # Flow Balancing
    for v in vehicles:
        for h in orders[1:-1]:
            prob += lpSum(x[(i,h,v)] for i in orders[:-1] if (i,h,v) in x) == lpSum(x[(h,j,v)] for j in orders[1:] if (h,j,v) in x)

    print("Finished modelling Flow Balancing")
    sys.stdout.flush()

    # Each customer is visited exactly once
    for i in orders[1:-1]:
        aux_sum=0
        for v in vehicles:
            aux_sum += lpSum(x[(i,j,v)] for j in orders[1:] if (i,j,v) in x) 
        prob += aux_sum ==1
    
    # for j in orders[1:-1]:
    #     aux_sum=0
    #     for v in vehicles:
    #         aux_sum += lpSum(x[(i,j,v)] for i in orders[:-1] if (i,j,v) in x) 
    #     prob += aux_sum ==1
    print("Finished modelling Each customer is visited exactly once")
    sys.stdout.flush()


    # Vehicle capacity constraint    
    for v in vehicles:
        aux_sum = 0
        for j in orders:
            aux_sum += lpSum([demands[i][1]*x[(i,j,v)] for i in orders[1:-1] if (i,j,v) in x]) 
        prob += aux_sum <= int(vehicles_dict[v][1])*I[v]
    print("Finished modelling Vehicle capacity constraint")
    sys.stdout.flush()

    # Time window constraints
    #considering time in minutes a_i = 08:00 = 480 mins and b_i = 22:00 = 1320 mins
    for v in vehicles:        #wait_time ignored
        for i in orders[:-1]:
            for j in orders[1:]:
                if i!=j and (i,j,v) in x:
                    prob += s[(i,v)] + 20 + return_dist_time(i,j)[1] - 1e8*(1- x[(i,j,v)]) <= s[(j,v)]

    print("Finished modelling Time window constraints")
    sys.stdout.flush()

    
    # Linking constraints
    for v in vehicles:
        for i in orders[:-1]:
            for j in orders[1:]:
                if i!=j and (i,j,v) in x:
                    prob += x[(i,j,v)] <= I[(v)]

    print("Finished modelling Linking constraints")
    sys.stdout.flush()

    
    # #Vehicle Compatibility
    # for i in orders[:-1]:
    #     for j in orders[1:]:
    #         for v in vehicles:
    #             if i!=j and (i,j,v) in x:
    #                 if (v in order_vehicle_id[i]) and (v in order_vehicle_id[j]):
    #                     x[(i,j,v)] <= I[v]
    #                 else:
    #                     x[(i,j,v)] == 0
    # print("Finished Vehicle Compatibility constraints")
    
    # *********************************
    # Solve the problem
    # *********************************
    solver = 'GUROBI' 
    print('-'*50)
    print('Optimization solver', solver , 'called')
    prob.writeLP("../output/cvrptw_14J.lp")
    prob.writeMPS("../output/cvrptw_14J.mps")
    # print(prob)
    if solver == 'GUROBI':
        prob.solve(GUROBI(MIPFocus=2,Cuts=3)) #,timeLimit=500,gapRel=0.1))
    else:
        prob.solve()

    # Print the status of the solved LP
    print("Status:", LpStatus[prob.status])
    sys.stdout.flush()
    print("objective=", value(prob.objective))
    sys.stdout.flush()

    print(f'Validation')
    sys.stdout.flush()
    print(f'Post processing to get routes of each vehicle')
    sys.stdout.flush()
    vx = {}   #{'truck_id':[i,j]}
    for v in vehicles:
        vx.update({v:[]})
        for var in prob.variables():
            if var.varValue == 1:
                x_list = var.name.split('#')
                if x_list[0] == 'x':
                    if x_list[3] == v:
                        vx[v].append(var.name)

    def extract_linked_identifiers(entries):
        parts =[]
        for entry in entries:
            part = entry.split('#')[1:-1]  # Remove 'x' and the suffix
            parts.append(part)
        return parts

    vehicleRoute = {}
    travel_dist = []
    for key, values in vx.items():
        links = extract_linked_identifiers(values)
        route = []
        while links:
            for link in links:
                if 'INV_source_00' == link[0]:
                    route.append(link[0])
                    route.append(link[1])
                    links.remove(link)
                if len(route) > 0:
                    if route[-1] == link[0]:
                        route.append(link[1])
                        links.remove(link)
        vehicleRoute.update({key:route})
        if len(route) > 0:
            print(key,route)
            sys.stdout.flush()
            print('\n')
            sys.stdout.flush()

        links = extract_linked_identifiers(values)
        # print(links)
        if len(links) >0:
            print(f"Truck {key}")
            sys.stdout.flush()
        cap = vehicles_dict[key][1]
        #cumulative weights of orders served
        wt=0
        #Distance covered by each truck:
        dist = 0
        if len(links) >0:
            for link in links:
                dist+=return_dist_time(link[0],link[1])[0]
            for order in route[1:-1]:    
                wt+=demands[order][1]  
            print(f"Capacity {cap} total weights served {wt} total distance covered {dist}")
            sys.stdout.flush()
            print('\n')
            travel_dist.append(dist)

    print(f"Total Travel Distance of all trucks {sum(travel_dist)}")
    sys.stdout.flush()

    print(f'Time Window validation')
    sys.stdout.flush()
    for key,val in vehicleRoute.items():
        siv_list=[]
        for order in val:
            siv = (order,key)
            siv_list.append((order,s[siv].varValue))
        if len(siv_list)>0:
            print(key,siv_list)
            sys.stdout.flush()
            print('\n')
            sys.stdout.flush()                                                            

if __name__ == "__main__":
    objective_1 = False   # Minimize the number of vehicles used
    objective_2 = False  # Minimize total travel distance
    objective_3 = True  # Minimize total cost
    build_model(orders,vehicles,demands,vehicles_dict,order_vehicle_id)

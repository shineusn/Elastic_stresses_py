# Running dc3d, given an input namedtuple.


import numpy as np 
import matplotlib.pyplot as plt 
import sys
from okada_wrapper import dc3dwrapper, dc3d0wrapper
import coulomb_collections
import conversion_math


def do_stress_computation(params, inputs, disp_points):
	# Step 0. Split receiver fault into many sub-faults if necessary
	# Step 1. Compute strains and displacements
	# Step 2. Resolve stresses on receiver faults

	print("Beginning stress calcultaion.");
	print("Number of sources: %d " % len(inputs.source_object));
	print("Number of receivers: %d " % len(inputs.receiver_object));
	subfaulted_inputs = split_subfault_receivers(params, inputs);
	
	# Refactoring here. 
	[x, y, x2d, y2d, u_displacements, v_displacements, w_displacements] = compute_grid_def(params, subfaulted_inputs);
	[u_ll, v_ll, w_ll] = compute_ll_def(params, subfaulted_inputs, disp_points);
	[receiver_normal, receiver_shear, receiver_coulomb] = compute_strains_stresses(params, subfaulted_inputs);

	MyOutObject = coulomb_collections.Out_object(x=x,y=y,x2d=x2d, y2d=y2d, u_disp=u_displacements, v_disp=v_displacements, w_disp=w_displacements, 
		u_ll=u_ll, v_ll=v_ll, w_ll=w_ll, 
		source_object=inputs.source_object, receiver_object=subfaulted_inputs.receiver_object, receiver_normal=receiver_normal, receiver_shear=receiver_shear, 
		receiver_coulomb=receiver_coulomb); 
	return MyOutObject;



def split_subfault_receivers(params,inputs):
	strike_split = params.strike_num_receivers;
	dip_split = params.dip_num_receivers;

	if strike_split==1 and dip_split==1:
		# If we're not splitting the subfaults...
		subfaulted_receivers=inputs.receiver_object;
		print("Not subdividing receiver faults further.");
	else:
		subfaulted_receivers=[];
		print("Splitting %d receiver faults into %d subfaults each." % (len(inputs.receiver_object), strike_split*dip_split) );

		for fault in inputs.receiver_object:  # for each receiver... 
			# We find the depths corresponding to the tops and bottoms of our new sub-faults
			zsplit_array = get_split_z_array(fault.top,fault.bottom,dip_split);

			for j in range(dip_split):  # First we split it up by dip. 
				# Get the new coordinates of the top of the fault plane. 
				W = conversion_math.get_downdip_width(fault.top,zsplit_array[j],fault.dipangle);
				vector_mag = W*np.cos(np.deg2rad(fault.dipangle));  # how far the bottom edge is displaced downdip from map-view

				# Get the starting points for the next row of fault subpatches. 
				[start_x_top, start_y_top] = conversion_math.add_vector_to_point(fault.xstart,fault.ystart,vector_mag,fault.strike+90);
				[finish_x_top, finish_y_top] = conversion_math.add_vector_to_point(fault.xfinish,fault.yfinish,vector_mag,fault.strike+90);

				[xsplit_array, ysplit_array] = get_split_x_y_arrays(start_x_top, finish_x_top, start_y_top, finish_y_top, strike_split);

				for k in range(strike_split):
					single_subfaulted_receiver = coulomb_collections.Faults_object(xstart=xsplit_array[k], 
						xfinish=xsplit_array[k+1], ystart=ysplit_array[k], yfinish=ysplit_array[k+1], 
						Kode=fault.Kode, rtlat=0, reverse=0, potency=[], 
						strike=fault.strike, dipangle=fault.dipangle, rake=fault.rake, 
						top=zsplit_array[j], bottom=zsplit_array[j+1], comment=fault.comment);
					subfaulted_receivers.append(single_subfaulted_receiver);
	
	subfaulted_objects = coulomb_collections.Input_object(PR1=inputs.PR1,FRIC=inputs.FRIC,depth=inputs.depth,start_gridx=inputs.start_gridx, finish_gridx=inputs.finish_gridx, 
		start_gridy=inputs.start_gridy, finish_gridy=inputs.finish_gridy, xinc=inputs.xinc, yinc=inputs.yinc, minlon=inputs.minlon,maxlon=inputs.maxlon,
		zerolon=inputs.zerolon,minlat=inputs.minlat,maxlat=inputs.maxlat,zerolat=inputs.zerolat,
		source_object=inputs.source_object, receiver_object=subfaulted_receivers);

	return subfaulted_objects;



def get_split_x_y_arrays(start_x_top, finish_x_top, start_y_top, finish_y_top, strike_split):
	# Take the coordinates of the top of a receiver fault plane. 
	# Generate the list of coordinates that will help split it up along-strike
	if start_x_top==finish_x_top:
		xsplit_array = [start_x_top for j in range(strike_split+1)];
	else:
		xincrement = (finish_x_top-start_x_top)/strike_split;
		xsplit_array = np.arange(start_x_top,finish_x_top+xincrement,xincrement);  
		# length : xsplit+1. contains all the xlocations that could be used as start-stop points in the top row. 
	if start_y_top==finish_y_top:
		ysplit_array = [start_y_top for j in range(strike_split+1)];
	else:
		yincrement = (finish_y_top-start_y_top)/strike_split;
		ysplit_array = np.arange(start_y_top,finish_y_top+yincrement,yincrement); 
		# length : xsplit+1. contains all the ylocations that could be used as start-stop points in the top row. 
	return [xsplit_array, ysplit_array] ;


def get_split_z_array(top,bottom,dip_split):
	if top==bottom:
		zsplit_array = [top for j in range(dip_split+1)];
	else:
		zincrement = abs(top-bottom)/dip_split;
		zsplit_array = np.arange(top,bottom+zincrement,zincrement); 
	return zsplit_array;


def compute_grid_def(params, inputs):
	# Loop through a grid and compute the displacements at each point from all sources put together. 
	x=np.linspace(inputs.start_gridx,inputs.finish_gridx,int((inputs.finish_gridx-inputs.start_gridx)/inputs.xinc));
	y=np.linspace(inputs.start_gridy,inputs.finish_gridy,int((inputs.finish_gridy-inputs.start_gridy)/inputs.yinc));
	[x2d,y2d] = np.meshgrid(x,y);
	u_displacements = np.zeros((len(y), len(x)));
	v_displacements = np.zeros((len(y), len(x)));
	w_displacements = np.zeros((len(y), len(x)));
	numrows=np.shape(u_displacements)[0]
	numcols=np.shape(u_displacements)[1]
	for ky in range(numrows):
		for kx in range(numcols):
			u_disp, v_disp, w_disp = compute_surface_disp_point(params, inputs, x2d[ky][kx], y2d[ky][kx]);
			u_displacements[ky][kx]= u_disp;
			v_displacements[ky][kx]= v_disp;
			w_displacements[ky][kx]= w_disp;
	return [x, y, x2d, y2d, u_displacements, v_displacements, w_displacements];


def compute_ll_def(params, inputs, disp_points):
	# Loop through a list of lon/lat and compute their displacements due to all sources put together. 
	x=[]; y=[];
	for i in range(len(disp_points.lon)):
		[xi,yi]=conversion_math.latlon2xy(disp_points.lon[i],disp_points.lat[i],inputs.zerolon,inputs.zerolat);
		x.append(xi);
		y.append(yi);

	u_ll = np.zeros(len(x));
	v_ll = np.zeros(len(x));
	w_ll = np.zeros(len(x));

	# For each coordinate requested. 
	for k in range(len(x)):
		u_disp, v_disp, w_disp = compute_surface_disp_point(params, inputs, x[k], y[k]);
		u_ll[k] = u_disp;
		v_ll[k] = v_disp;
		w_ll[k] = w_disp;

	return [u_ll, v_ll, w_ll];


def compute_surface_disp_point(params, inputs, x, y):
	# A major compute loop for each source object at an x/y point. 
	# x/y in the same coordinate system as the fault object. 
	u_disp = 0; v_disp=0; w_disp=0;
	for fault in inputs.source_object:

		# Fault parameters
		L = conversion_math.get_strike_length(fault.xstart,fault.xfinish,fault.ystart,fault.yfinish);
		W = conversion_math.get_downdip_width(fault.top,fault.bottom,fault.dipangle);
		depth       = fault.top;
		dip         = fault.dipangle;
		strike_slip = fault.rtlat*-1;  # The dc3d coordinate system has left-lateral positive. 
		dip_slip    = fault.reverse;

		# Preparing to rotate to a fault-oriented coordinate system.
		theta=fault.strike-90;
		theta=np.deg2rad(theta);
		R=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
		R2=np.array([[np.cos(-theta),-np.sin(-theta)],[np.sin(-theta),np.cos(-theta)]])
 
		# Compute the position relative to the translated, rotated fault. 
		translated_pos = np.array([[x-fault.xstart],[y-fault.ystart]]);
		xy=R.dot(translated_pos);
		# Solve for displacements at the surface
		if fault.potency != []:
			success, u, grad_u = dc3d0wrapper(params.alpha, [xy[0], xy[1], 0.0], depth, dip, 
				[fault.potency[0], fault.potency[1], fault.potency[2], fault.potency[3]]);  
			u=u*1e-6;  # Unit correction: potency from N-m results in displacements in microns. 
		else:
			success, u, grad_u = dc3dwrapper(params.alpha, [xy[0], xy[1], 0.0], depth, dip, [0, L], [-W, 0], [strike_slip, dip_slip, 0.0]); 
		urot=R2.dot(np.array([[u[0]], [u[1]]]));

		# Update the displacements from all sources 
		u_disp=u_disp + urot[0];
		v_disp=v_disp + urot[1];
		w_disp=w_disp + u[2];  # vertical

	return u_disp, v_disp, w_disp;



def compute_strains_stresses(params, inputs):

	# Pseudocode: 
	# For each receiver, at the center point, sum up the strain and stress for each source.
	# Return : source object, receiver object, shear stress, normal stress, and coulomb stress on each receiver. 
	
	# The values we're actually going to output. 
	receiver_shear=[];
	receiver_normal=[];
	receiver_coulomb=[];

	for receiver in inputs.receiver_object:
		centercoords = conversion_math.get_fault_center(receiver);
		normal_sum=0;
		shear_sum=0;
		coulomb_sum=0;

		for source in inputs.source_object:
		# A major compute loop for each source object. 

			L = conversion_math.get_strike_length(source.xstart,source.xfinish,source.ystart,source.yfinish);
			W = conversion_math.get_downdip_width(source.top,source.bottom,source.dipangle);
			depth       = source.top;
			dip         = source.dipangle;
			strike_slip = source.rtlat*-1; # The dc3d coordinate system has left-lateral positive. 
			dip_slip    = source.reverse;

			# Preparing to rotate to a fault-oriented coordinate system.
			theta=source.strike-90;
			theta=np.deg2rad(theta);
			R=np.array([[np.cos(theta),-np.sin(theta), 0],[np.sin(theta),np.cos(theta), 0],[0,0,1]]);  # horizontal rotation into strike-aligned coordinates.
			R2=np.array([[np.cos(-theta),-np.sin(-theta),0],[np.sin(-theta),np.cos(-theta),0],[0,0,1]]); 
			
			# Compute the position relative to the translated, rotated fault. 
			translated_pos = np.array([[centercoords[0]-source.xstart],[centercoords[1]-source.ystart],[-centercoords[2]] ]);
			xyz=R.dot(translated_pos);
			if source.potency != []:
				success, u, grad_u = dc3d0wrapper(params.alpha, [xyz[0], xyz[1], xyz[2]], depth, dip, 
					[source.potency[0], source.potency[1], source.potency[2], source.potency[3]]); 
				grad_u = grad_u * 1e-9; # DC3D0 Unit correction: potency from N-m results in displacements in nanostrain
			else:
				success, u, grad_u = dc3dwrapper(params.alpha, [xyz[0], xyz[1], xyz[2]], depth, dip, [0, L], [-W, 0], [strike_slip, dip_slip, 0.0]);  
				grad_u = grad_u * 1e-3;  # DC3D Unit correction. 
			# Solve for displacement gradients at center of receiver fault

			# Rotate grad_u back into the unprimed coordinates.  Divide by 1000 because coordinate units (km) and slip units (m) are different by 1000. 
			desired_coords_grad_u = np.dot(R2, np.dot(grad_u, R2.T));
			
			# Then rotate again into receiver coordinates. 
			strain_tensor=conversion_math.get_strain_tensor(desired_coords_grad_u);
			stress_tensor=conversion_math.get_stress_tensor(strain_tensor, params.lame1, params.mu);

			# Then compute shear, normal, and coulomb stresses. 
			[normal, shear, coulomb]=conversion_math.get_coulomb_stresses(stress_tensor,receiver.strike,receiver.rake,receiver.dipangle,inputs.FRIC);
			normal_sum=normal_sum+normal;
			shear_sum=shear_sum+shear;
			coulomb_sum=coulomb_sum+coulomb;

		receiver_normal.append(normal_sum);
		receiver_shear.append(shear_sum);
		receiver_coulomb.append(coulomb_sum);

		# return lists of normal, shear, coulomb values for each receiver. 
	return [receiver_normal, receiver_shear, receiver_coulomb]; 	


"""



"""


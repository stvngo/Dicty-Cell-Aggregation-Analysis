"""
Utility functions for notebook analysis.
"""
import plotly.graph_objects as go
import plotly.io as pio
import imageio.v2 as imageio
import numpy as np
import matplotlib.pyplot as plt

def save_gif(fig, filename):
    frames = []
    # Rotate camera around z-axis to create an animation (36 frames ~ one full turn)
    for angle in np.linspace(0, 360, 36):
        fig.update_layout(
            scene_camera=dict(
                eye=dict(
                    x=1.8 * np.cos(np.radians(angle)),
                    y=1.8 * np.sin(np.radians(angle)),
                    z=1.2,
                )
            )
        )
        # Use Plotly's default engine (Kaleido) without specifying `engine=` to avoid deprecation spam
        img_bytes = fig.to_image(format="png")
        frame = imageio.imread(img_bytes, format="png")
        frames.append(frame)

    imageio.mimsave(f"assets/img/{filename}", frames, duration=0.12, loop=0)
    print(f"Saved GIF to assets/img/{filename}")

# Helper function to create 3D distribution plots for any feature combination
def plot_3d_distribution(feature1_name, feature2_name, data_df, 
                         n_bins1=50, n_bins2=50, plot_type='both', 
                         smooth_sigma=1.0, title_suffix=""):
    """
    Create a 3D distribution plot showing frequency of (feature1, feature2) combinations.
    
    Parameters:
    - feature1_name: Name of first feature (x-axis)
    - feature2_name: Name of second feature (y-axis)  
    - data_df: DataFrame containing the data
    - n_bins1, n_bins2: Number of bins for each feature
    - plot_type: 'bar', 'surface', or 'both' (default: 'both')
    - smooth_sigma: Gaussian smoothing sigma (0 = no smoothing, default: 1.0)
    - title_suffix: Additional text for title
    """
    from mpl_toolkits.mplot3d import Axes3D
    from scipy.ndimage import gaussian_filter
    
    feature1_data = data_df[feature1_name].values
    feature2_data = data_df[feature2_name].values
    
    # Create bins
    feature1_bins = np.linspace(feature1_data.min(), feature1_data.max(), n_bins1 + 1)
    feature2_bins = np.linspace(feature2_data.min(), feature2_data.max(), n_bins2 + 1)
    
    # Compute 2D histogram
    H, feature1_edges, feature2_edges = np.histogram2d(
        feature1_data, 
        feature2_data, 
        bins=[feature1_bins, feature2_bins]
    )
    
    # Smooth histogram for surface plot
    H_smooth = gaussian_filter(H, sigma=smooth_sigma) if smooth_sigma > 0 else H
    
    # Get bin centers
    feature1_centers = (feature1_edges[:-1] + feature1_edges[1:]) / 2
    feature2_centers = (feature2_edges[:-1] + feature2_edges[1:]) / 2
    
    # Create meshgrid
    F1_mesh, F2_mesh = np.meshgrid(feature1_centers, feature2_centers, indexing='ij')
    
    # Plot bar chart if requested
    if plot_type in ['bar', 'both']:
        fig = plt.figure(figsize=(14, 10))
        ax = fig.add_subplot(111, projection='3d')
        
        # Plot as 3D bar chart
        nonzero_mask = H > 0
        x_pos = F1_mesh[nonzero_mask]
        y_pos = F2_mesh[nonzero_mask]
        z_pos = np.zeros_like(x_pos)
        dx = (feature1_edges[1] - feature1_edges[0]) * 0.8
        dy = (feature2_edges[1] - feature2_edges[0]) * 0.8
        dz = H[nonzero_mask]
        
        # Color bars by frequency
        if dz.max() > 0:
            colors = plt.cm.viridis(dz / dz.max())
        else:
            colors = plt.cm.viridis(np.zeros_like(dz))
        
        ax.bar3d(x_pos, y_pos, z_pos, dx, dy, dz, color=colors, alpha=0.6, 
                 edgecolor='black', linewidth=0.1)
        
        ax.set_xlabel(feature1_name, fontsize=12, labelpad=10)
        ax.set_ylabel(feature2_name, fontsize=12, labelpad=10)
        ax.set_zlabel('Frequency (Density)', fontsize=12, labelpad=10)
        ax.set_title(f'3D Distribution (Bar Chart): {feature1_name} vs {feature2_name} vs Frequency{title_suffix}', 
                     fontsize=14, pad=20)
        
        # Add colorbar
        if dz.max() > 0:
            sm = plt.cm.ScalarMappable(cmap=plt.cm.viridis, 
                                       norm=plt.Normalize(vmin=dz.min(), vmax=dz.max()))
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=ax, shrink=0.5, aspect=20, pad=0.1)
            cbar.set_label('Frequency', fontsize=10)
        
        ax.view_init(elev=30, azim=45)
        plt.tight_layout()
        plt.show()
    
    # Plot surface if requested
    if plot_type in ['surface', 'both']:
        fig = plt.figure(figsize=(14, 10))
        ax = fig.add_subplot(111, projection='3d')
        
        # Plot surface
        surf = ax.plot_surface(
            F1_mesh, 
            F2_mesh, 
            H_smooth.T,  # Transpose for correct orientation
            cmap='viridis',
            alpha=0.8,
            linewidth=0,
            antialiased=True
        )
        
        # Add contour lines on the base
        contour = ax.contour(
            F1_mesh, 
            F2_mesh, 
            H_smooth.T,
            zdir='z',
            offset=0,
            cmap='viridis',
            alpha=0.5,
            linewidths=1
        )
        
        ax.set_xlabel(feature1_name, fontsize=12, labelpad=10)
        ax.set_ylabel(feature2_name, fontsize=12, labelpad=10)
        ax.set_zlabel('Frequency (Density)', fontsize=12, labelpad=10)
        ax.set_title(f'3D Distribution (Surface): {feature1_name} vs {feature2_name} vs Frequency{title_suffix}', 
                     fontsize=14, pad=20)
        
        # Add colorbar
        fig.colorbar(surf, ax=ax, shrink=0.5, aspect=20, pad=0.1, label='Frequency')
        
        ax.view_init(elev=30, azim=45)
        plt.tight_layout()
        plt.show()
    
    # Print statistics
    print(f"\nStatistics for {feature1_name} vs {feature2_name}:")
    print(f"Total data points: {len(data_df)}")
    print(f"{feature1_name} range: [{feature1_data.min():.3f}, {feature1_data.max():.3f}]")
    print(f"{feature2_name} range: [{feature2_data.min():.3f}, {feature2_data.max():.3f}]")
    print(f"Max frequency in bin: {H.max()}")
    print(f"Bins with data: {np.sum(H > 0)} / {H.size}")


def plot_interactive_3d_surface(merged):
    """
    Interactive 3D surface: Cosine vs EDGE_TIME vs Frequency.

    Uses Plotly for fully interactive rotation/zoom.
    This is a direct lift of the original notebook cell.
    """
    import numpy as np
    import plotly.graph_objects as go
    import plotly.io as pio

    # Ensure a notebook-friendly renderer so the plot actually displays
    # You can change this to 'browser' if needed
    pio.renderers.default = 'notebook_connected'
    print(f"Plotly renderer: {pio.renderers.default}")

    # Use EDGE_TIME on x-axis, cosine on y-axis, frequency on z-axis
    if 'EDGE_TIME' in merged.columns:
        time_vals = merged['EDGE_TIME'].values
        time_label = 'Edge Time (T)'
    else:
        time_vals = ((merged['POSITION_T_source'] + merged['POSITION_T_target']) / 2).values
        time_label = 'Time (T) - Midpoint'

    cos_vals = merged['cosine'].values

    # Define bins (same as original)
    n_time_bins = 60
    n_cos_bins = 60

    time_bins = np.linspace(time_vals.min(), time_vals.max(), n_time_bins + 1)
    cos_bins = np.linspace(-1, 1, n_cos_bins + 1)

    # 2D histogram: counts in each (time, cosine) bin
    H, time_edges, cos_edges = np.histogram2d(time_vals, cos_vals, bins=[time_bins, cos_bins])

    # Bin centers
    time_centers = (time_edges[:-1] + time_edges[1:]) / 2
    cos_centers = (cos_edges[:-1] + cos_edges[1:]) / 2

    # Create meshgrid for surface
    Time_mesh, Cos_mesh = np.meshgrid(time_centers, cos_centers, indexing='ij')

    # Plotly expects 2D arrays for x, y, z; use meshgrid + histogram
    fig = go.Figure(
        data=[
            go.Surface(
                x=Time_mesh,
                y=Cos_mesh,
                z=H,
                colorscale='Viridis',
                colorbar=dict(title='Edge Count'),
                showscale=True,
            )
        ]
    )

    fig.update_layout(
        title='Interactive 3D Surface: Cosine vs Time vs Frequency',
        scene=dict(
            xaxis_title=time_label,
            yaxis_title='Cosine (alignment with wave)',
            zaxis_title='Edge Count',
            xaxis=dict(backgroundcolor='rgba(0,0,0,0)'),
            yaxis=dict(backgroundcolor='rgba(0,0,0,0)'),
            zaxis=dict(backgroundcolor='rgba(0,0,0,0)'),
        ),
        autosize=True,
        width=900,
        height=700,
    )

    fig.show()

    print(f"Time range: {time_vals.min():.1f} to {time_vals.max():.1f}")
    print(f"Cosine range: {cos_vals.min():.3f} to {cos_vals.max():.3f}")
    print(f"Max bin count: {H.max()} edges")
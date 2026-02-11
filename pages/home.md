---
layout: home
title: Dictyostelium Motility and Cell Aggregation Dynamics
description: Biophysics and Computer Vision Research Project - Cell Tracking and Velocity Analysis
permalink: /
background: {{ site.baseurl }}/assets/img/trial_3_cell_tracks.png
---

# Dictyostelium Motility and Cell Aggregation Dynamics

**Biophysics and Computer Vision Research Project** under *Dr. Wouter-Jan Rappel* and *PhD Student Yi-Chieh Lai* at **UCSD Department of Physics**.

<p align="center">
  <img src="{{ site.baseurl }}/assets/img/cell_tracking_1.gif" alt="Cell tracking trajectories" height="260"/>
  <img src="{{ site.baseurl }}/assets/img/cosine_vs_time_surface_long.gif" alt="Cosine vs Time Surface" height="260"/>
</p>

## Introduction

*Dictyostelium discoideum* is a social amoeba that, upon starvation, initiates a collective aggregation process to survive. Individual cells chemotax toward waves of cAMP, forming complex streaming patterns, mounds, and eventually a migrating multicellular slug. This process, regulated by **cAMP** signaling and cell adhesion, leads to the formation of a fruiting body.

## Research Objectives

- Process TIFF file(s) from lab via thresholding.
- Each frame is 15 seconds.
- There are thousands of amoeba cells in movie, aggregating into 6 large cells by the end of the film.
- Use **ImageJ/Fiji's** built-in cell tracking algorithms (**TrackMate**) and libraries to model the position and velocity of a subset of these cells over time, particularly:
    - their movement *parallel/orthogonal to the Flamindo2 band*, and 
    - their movement *relative to each other/cluster centers*.

## Problems

The cells contain a fluorescent marker, called **Flamindo2**, which goes dark if the intracellular cAMP concentration is high. **Cyclic AMP (cAMP)** is the chemoattractant, in other words, the chemical the cells respond to under starvation. These waves of cyclic AMP sweep over the cells in a periodic fashion. Cells relay the chemoattractant signal: if they experience a high cyclic AMP concentration around their cell body, they begin to make cAMP and will secrete it, causing them to become **dark**.

The presence of this global wave/band of Flamindo2 moving from the top-right to the bottom-left of the (subset) of the Petri dish from the laboratory causes cells to move out of vision during thresholding, which poses a large challenge.

The **field of view is also much smaller** than the experimental Petri dish (cells may move out of frame), so **we do not know where these waves originate from**.

## Solutions

**1. Analyze a window/subset of the TIFF movie for a proof of concept**
- Even if it is for a few seconds, model the movement of the cells between the bands before the cells begin to disappear.
- Select a subset or a window of the TIFF movie;

**2. Persist the tracking of cells during disappearance if they have not moved too far**
- Keep tracking the cells' location when they have disappeared, freezing the tracker's position of the cell before it disappears, and continue tracking after it reappears.

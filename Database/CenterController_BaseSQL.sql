-- phpMyAdmin SQL Dump
-- version 4.7.6
-- https://www.phpmyadmin.net/
--
-- Host: localhost
-- Generation Time: Jun 27, 2018 at 10:09 AM
-- Server version: 5.5.58-0ubuntu0.14.04.1
-- PHP Version: 5.5.9-1ubuntu4.22

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET AUTOCOMMIT = 0;
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `Open-SD-WAN`
--

-- --------------------------------------------------------

--
-- Table structure for table `device`
--

CREATE TABLE `device` (
  `did` int(11) NOT NULL,
  `hostname` text NOT NULL,
  `type` text NOT NULL,
  `ipaddr` text NOT NULL,
  `lid` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `flow_table`
--

CREATE TABLE `flow_table` (
  `fid` int(11) NOT NULL,
  `dpid` int(11) NOT NULL,
  `vni` int(11) NOT NULL,
  `start` int(11) NOT NULL,
  `end` int(11) NOT NULL,
  `category` text NOT NULL,
  `flow_match` text NOT NULL,
  `actions` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `location`
--

CREATE TABLE `location` (
  `lid` int(11) NOT NULL,
  `location` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `physical_link`
--

CREATE TABLE `physical_link` (
  `phyid` int(11) NOT NULL,
  `port_id1` int(11) NOT NULL,
  `port_id2` int(11) NOT NULL,
  `live` tinyint(1) NOT NULL,
  `vlan1` int(11) NOT NULL,
  `vlan2` int(11) NOT NULL,
  `nw_type` text NOT NULL,
  `weight` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `port`
--

CREATE TABLE `port` (
  `port_id` int(11) NOT NULL,
  `did` int(11) NOT NULL,
  `interface` int(11) NOT NULL,
  `macaddr` text NOT NULL,
  `type` text NOT NULL,
  `dpdk` tinyint(1) NOT NULL,
  `global_ip` text NOT NULL,
  `local_ip` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `vnilist`
--

CREATE TABLE `vnilist` (
  `vxlanid` int(11) NOT NULL,
  `path` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

--
-- Indexes for dumped tables
--

--
-- Indexes for table `device`
--
ALTER TABLE `device`
  ADD PRIMARY KEY (`did`);

--
-- Indexes for table `flow_table`
--
ALTER TABLE `flow_table`
  ADD PRIMARY KEY (`fid`),
  ADD UNIQUE KEY `fid` (`fid`);

--
-- Indexes for table `location`
--
ALTER TABLE `location`
  ADD PRIMARY KEY (`lid`);

--
-- Indexes for table `physical_link`
--
ALTER TABLE `physical_link`
  ADD PRIMARY KEY (`phyid`);

--
-- Indexes for table `port`
--
ALTER TABLE `port`
  ADD PRIMARY KEY (`port_id`);

--
-- Indexes for table `vnilist`
--
ALTER TABLE `vnilist`
  ADD PRIMARY KEY (`vxlanid`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `flow_table`
--
ALTER TABLE `flow_table`
  MODIFY `fid` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `location`
--
ALTER TABLE `location`
  MODIFY `lid` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `physical_link`
--
ALTER TABLE `physical_link`
  MODIFY `phyid` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `vnilist`
--
ALTER TABLE `vnilist`
  MODIFY `vxlanid` int(11) NOT NULL AUTO_INCREMENT;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;

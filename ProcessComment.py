#!/usr/bin/env python3

import sys
import logging
import time
import configparser
import traceback

import praw
import prawcore
from psaw import PushshiftAPI

import DataCollector
import FlairManager

# PRAW instance for comment processing thread
praw_config = configparser.ConfigParser()
praw_config.read("praw.ini")
r = praw.Reddit(
    client_id=praw_config["InstaMod"]["client_id"],
    client_secret=praw_config["InstaMod"]["client_secret"],
    password=praw_config["InstaMod"]["password"],
    username=praw_config["InstaMod"]["username"],
    user_agent=praw_config["InstaMod"]["user_agent"]
)

# PushShift Instance
ps = PushshiftAPI(r)


# Get new comments as they are added to the queue by the producer thread
def fetch_queue(comment_queue, flair_queue, perm_queue, sub_list):
    # Loop continuously checking for new comments
    while True:
        comment = comment_queue.get()
        comment_queue.task_done()
        user = comment.author

        if user is None:
            try:
                logging.warning("User is None\n"
                                "Comment ID: " + comment.id)
            except prawcore.exceptions.NotFound:
                logging.critical("User is None and Comment ID is inaccessible")
            continue

        try:
            user.link_karma
        except (AttributeError, prawcore.NotFound):
            logging.warning("User: " + user.username + "is None\n"
                            "Comment ID: " + comment.id)
            continue

        logging.info("Processing comment from " + str(user))

        # Find sub that the comment was placed in
        target_sub = None
        comment_sub = str(comment.subreddit).lower()
        for sub in sub_list:
            if sub.name.lower() == comment_sub:
                target_sub = sub
                break
        if target_sub is None:
            logging.warning("Target sub not found: " + comment_sub)
            continue

        logging.info("Target sub found: " + comment_sub)

        # Check if the user data should be updated
        check_data = check_user(user, target_sub)
        update_flair = check_data[0]        # Does user's flair need to be updated
        scrape_data = check_data[1]         # Does user's data need to be updated
        user_in_accnt_info = check_data[2]  # Does the user's data need to be updated or inserted
        user_in_sub_info = check_data[3]    # Does the user have data for the target sub

        logging.info("Check User: " + str(user) +
                     "\n\tUpdate flair: " + str(update_flair) +
                     "\n\tScrape data: " + str(scrape_data) +
                     "\n\tIn accnt_info: " + str(user_in_accnt_info) +
                     "\n\tIn sub_info: " + str(user_in_sub_info))

        if scrape_data:
            logging.info("Collecting data...")
            try:
                DataCollector.load_data(user_in_accnt_info, user_in_sub_info, update_flair,
                                        user, target_sub, sub_list, ps)
            except:
                logging.warning("\nError in DataCollector for: {str(user)}\n" + str(sys.exc_info()[0]) + "\n")
                tb = traceback.format_exc()
                logging.warning("\nError in FlairManager for: {str(user)}\n" + str(tb) + "\n")
                r.redditor(praw_config["Bot Info"]["bot_owner"]).message("InstaMod Error for " + str(user),
                                                                         "DataCollector Stacktrace: \n\n" + tb)
                continue

        if update_flair:
            # Read flair toggles from sub config
            prog_flair_enabled = target_sub.main_config.getboolean("progression tier")
            new_accnt_flair_enabled = target_sub.main_config.getboolean("young account tag")
            activity_flair_enabled = target_sub.main_config.getboolean("activity tag")

            # If at least one flair toggle is enabled, update user flair
            if prog_flair_enabled or new_accnt_flair_enabled or activity_flair_enabled:
                logging.info("Updating flair...")
                try:
                    FlairManager.update_flair(flair_queue, perm_queue, comment.author, target_sub, prog_flair_enabled, new_accnt_flair_enabled, activity_flair_enabled)
                except:
                    tb = traceback.format_exc()
                    logging.warning("\nError in FlairManager for: {str(user)}\n" + str(tb) + "\n")
                    r.redditor(praw_config["Bot Info"]["bot_owner"]).message("InstaMod Error for " + str(user), "FlairManager Stacktrace: \n\n" + tb)
                    continue
            else:
                logging.debug("All flair settings disabled")


# Check if user should be skipped and if their data needs to be updated or inserted
def check_user(user, target_sub):
    # Turn comma delimited string into a list of whitelisted usernames
    user_whitelist = target_sub.flair_config["user whitelist"].lower().replace(" ", "").split(",")
    css_whitelist = target_sub.flair_config["css whitelist"].lower().replace(" ", "").split(",")
    username = str(user).lower()
    user_flair = next(target_sub.sub.flair(username))
    user_in_accnt_info = target_sub.db.exists_in_accnt_info(username)
    user_in_sub_info = target_sub.db.exists_in_sub_info(username)
    
    # Check if user is a mod or whitelisted
    if user in target_sub.mods or username in user_whitelist or user_flair["flair_css_class"] in css_whitelist:
        logging.info("User skipped because of mod or whitelist: " + str(user))
        update_flair = False
        scrape_data = False
    
    # User has been seen by the bot before
    elif user_in_accnt_info:
        # Check if user data has not been updated in the last 7 days
        last_scraped = target_sub.db.fetch_accnt_info(username, "last scraped")
        logging.debug("last_scraped: " + str(last_scraped))
        logging.debug("last_scraped type: " + str(type(last_scraped)))

        current_time = int(time.time())
        day_diff = int((current_time - last_scraped) / 86400)
        if day_diff > 7:
            scrape_data = True
        else:
            scrape_data = False
            
        # User has been seen in the subreddit before
        if user_in_sub_info:
            # Check if the user has used their custom flair permission
            custom_flair_used = target_sub.db.fetch_sub_info(username, "custom flair used") == 1
            # Check if the user is not permitted to receive custom flair
            no_auto_flair = target_sub.db.fetch_sub_info(username, "no auto flair") == 1
    
            # Get time the user was last updated
            last_updated = target_sub.db.fetch_sub_info(username, "last updated")
            current_time = int(time.time())
            day_diff = int((current_time - last_updated) / 86400)
    
            # If the user has used custom flair, is designated to not receive auto flair, or flair is not enabled,
            # only update data and not flair
            if custom_flair_used or no_auto_flair or \
                    (len(target_sub.progression_tiers) == 0 and len(target_sub.sub_activity) == 0):
                update_flair = False
            # Check if flair is expired
            elif day_diff >= target_sub.flair_config.getint("flair expiration"):
                update_flair = True
            else:
                update_flair = False
        
        # User has been seen before but not in this subreddit
        else:
            update_flair = True
        
    # User hasn't been seen before - pull all account data and update flair
    else:
        update_flair = True
        scrape_data = True
    
    return [update_flair, scrape_data, user_in_accnt_info, user_in_sub_info]

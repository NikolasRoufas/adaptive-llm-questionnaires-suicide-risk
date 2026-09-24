#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline controller for adaptive LLM-generated questionnaires.

Paper: Adaptive LLM-Generated Questionnaires for Suicide Risk Assessment:
       A Clinical Pilot in Greece (NICE TEAS Europe 2026).
"""
import os
import re
import argparse
import glob
import numpy as np
import pandas as pd
from tqdm import tqdm
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns

from adaptive_questionnaires.core.mark_i import MkI
from adaptive_questionnaires.clients.google_api import GoogleAPI, GoogleSheetsAPI
from adaptive_questionnaires.clients.openai_client import OpenaiAPI
from adaptive_questionnaires.clients.dropbox_client import DropboxAPI
from adaptive_questionnaires.legacy import algorithm as legacy
from adaptive_questionnaires.legacy.parsing import parse_questionnaire_markdown


class Controller():
    def __init__(self, mk1 : MkI) :
        self.mk1  = mk1
        self.args = self.parsing()

        self.__null_values = [
            None, np.nan, "", "#N/A", "null", "nan", "NaN", "None"
        ]


    def parsing(self):
        parser = argparse.ArgumentParser()

        ## ______________________________ General ______________________________ ##
        parser.add_argument(
            "--operation",
            "-o",
            type    = str,
            default = "task1",
            help    = "Options = {}",
        )
        
        return parser.parse_args()
    


    def run_initialization(self, use_openai: bool = True):
        """Wire Google Sheets + optional OpenAI for the adaptive questionnaire pipeline."""
        self.google_api = GoogleAPI(mk1=self.mk1)
        self.google_sheets_api = GoogleSheetsAPI(
            mk1=self.mk1,
            google_api=self.google_api,
        )
        if use_openai:
            self.openai_api = OpenaiAPI(mk1=self.mk1)

    def _refresh_session(self):
        self.run_initialization()

    def _refresh_tokens(self):
        """Optional: sync Google OAuth token from Dropbox (disabled in run() by default)."""
        self.dropbox_api = DropboxAPI(mk1=self.mk1)
        google_oauth_accessed_dbx_path = self.mk1.config.get(
            "dropbox", "google_oauth_accessed_dbx_path"
        )
        google_oauth_local_path = self.mk1.config.get("api_google", "token_file_path")
        google_oauth_accessed_local_path = (
            f"{google_oauth_local_path.rsplit('.', 1)[0]}_accessed.json"
        )
        self.dropbox_api.download_file(
            dropbox_path=google_oauth_accessed_dbx_path,
            local_path=google_oauth_accessed_local_path,
        ) 


    def run_task0(self):
        ## _______________ *** Configuration (attributes) *** _______________ #
        # args
        operation = self.args.operation

        # google sheets
        sheets_reporter_id          = self.mk1.config.get("google_sheets", "reporter_id")
        sheets_reporter_tab_input   = self.mk1.config.get("google_sheets", "reporter_tab_input")
        sheets_reporter_tab_output  = self.mk1.config.get("google_sheets", "reporter_tab_output")
        sheets_reporter_tab_prompts = self.mk1.config.get("google_sheets", "reporter_tab_prompts")

        ## _____________________________________________________________________________________________________________________ ##
        tqdm.pandas()
        input = self.google_sheets_api.get_df_from_tab(
            spreadsheet_id         = sheets_reporter_id,
            spreadsheet_range_name = sheets_reporter_tab_input,
            spreadsheet_has_index  = False,
        )

        output = self.google_sheets_api.get_df_from_tab(
            spreadsheet_id         = sheets_reporter_id,
            spreadsheet_range_name = sheets_reporter_tab_output,
            spreadsheet_has_index  = False,
        )

        prompts_info = self.google_sheets_api.get_df_from_tab(
            spreadsheet_id         = sheets_reporter_id,
            spreadsheet_range_name = sheets_reporter_tab_prompts,
            spreadsheet_has_index  = False,
        )

        prompt_info = prompts_info[
            prompts_info["task"] == "task_0"
        ]
        prompt       = prompt_info.loc[0, "prompt"]
        system_role  = prompt_info.loc[0, "system_role"]
        user_role    = prompt_info.loc[0, "user_role"]
        requirements = prompt_info.loc[0, "requirements"].strip().split("\n")
        examples     = prompt_info.loc[0, "examples"].strip().split("\n")


        # Iterate over each row
        for idx, row in tqdm(output.iterrows(), desc = "Loading ..."):

            check_q_exists = len(str(row[operation])) > 0 and str(row[operation]) not in self.__null_values
            if check_q_exists : continue  # already exists

            try:
                # Get the text content from the specified column
                variables   = {
                    "history" : str(row["history"])
                }
            
                # Execute the custom prompt
                result = self.openai_api.execute_custom_prompt(
                    prompt       = prompt,
                    variables    = variables,
                    system_role  = system_role,
                    user_role    = user_role,
                    requirements = requirements,
                    examples     = examples
                )

                # Fill in the target column with the result
                output.at[idx, operation] = result

                # write the result back
                self.google_sheets_api.write_df_to_tab(
                    df                     = output,
                    spreadsheet_id         = sheets_reporter_id,
                    spreadsheet_range_name = sheets_reporter_tab_output,
                ) 
                
            except Exception as e:
                raise e
                print(f"Error processing row {idx}: {str(e)}")
                output.at[idx, operation] = f"Error: {str(e)}"



    def run_task1_preparation(self):
        ## _______________ *** Configuration (attributes) *** _______________ #
        sheets_reporter_id         = self.mk1.config.get("google_sheets", "reporter_id")
        sheets_reporter_tab_output = self.mk1.config.get("google_sheets", "reporter_tab_output")

        ## _____________________________________________________________________________________________________________________ ##
        tqdm.pandas()

        # get the raw task0 content (assuming first col = metadata, second col = big text)
        task0_df = self.google_sheets_api.get_df_from_tab(
            spreadsheet_id         = sheets_reporter_id,
            spreadsheet_range_name = sheets_reporter_tab_output,
            spreadsheet_has_index  = False,
        )

        if task0_df.empty:
            raise ValueError("task0 is empty or missing")

        # Loop over all rows (all patients)
        for row_idx, row in task0_df.iterrows():
            raw_text = row[1]  # second column = the big "Κατηγορία" text
            if pd.isna(raw_text):
                print(f"⚠️ Row {row_idx} is empty, skipping")
                continue

            # tab name = patient{row_position+2}
            sheet_name = f"patient{row_idx+3}"
            
            # Check if tab already exists
            if self.google_sheets_api.sheet_exists(sheets_reporter_id, sheet_name):
                print(f"ℹ️ Sheet '{sheet_name}' already exists, skipping creation")
                continue

            report = parse_questionnaire_markdown(raw_text)
            df = legacy.initial_block_rows(report.items)

            # Only create sheet if it doesn't exist (already checked above)
            self.google_sheets_api.ensure_sheet_exists(
                spreadsheet_id = sheets_reporter_id, 
                sheet_name = sheet_name
            )

            # write to google sheets (create/overwrite tab)
            self.google_sheets_api.write_df_to_tab2(
                df = df,
                spreadsheet_id = sheets_reporter_id,
                tab_name = sheet_name        
            )

            # Apply formatting
            self.google_sheets_api.format_sheet_tab(
                spreadsheet_id=sheets_reporter_id, 
                tab_name=sheet_name, 
                df=df
            )

            print(f"✅ Created/updated sheet: {sheet_name}")
            print(df.head())




    def run_task1(self):
        ## _______________ *** Configuration (attributes) *** _______________ #
        sheets_reporter_id          = self.mk1.config.get("google_sheets", "reporter_id")
        sheets_reporter_tab_output  = self.mk1.config.get("google_sheets", "reporter_tab_output")
        sheets_reporter_tab_prompts = self.mk1.config.get("google_sheets", "reporter_tab_prompts")

        ## _____________________________________________________________________________________________________________________ ##
        tqdm.pandas()

        # prompts 
        prompts_info = self.google_sheets_api.get_df_from_tab(
            spreadsheet_id         = sheets_reporter_id,
            spreadsheet_range_name = sheets_reporter_tab_prompts,
            spreadsheet_has_index  = False,
        )

        prompt_info = prompts_info[
            prompts_info["task"] == "task_1"
        ].reset_index(drop = True)
        prompt       = prompt_info.loc[0, "prompt"]
        system_role  = prompt_info.loc[0, "system_role"]
        user_role    = prompt_info.loc[0, "user_role"]
        requirements = prompt_info.loc[0, "requirements"]
        examples     = str(prompt_info.loc[0, "examples"] or "").strip().split("\n") if pd.notna(prompt_info.loc[0, "examples"]) else []


        # get the raw task0 content (assuming first col = metadata, second col = big text)
        output_df = self.google_sheets_api.get_df_from_tab(
            spreadsheet_id         = sheets_reporter_id,
            spreadsheet_range_name = sheets_reporter_tab_output,
            spreadsheet_has_index  = False,
        )

        if output_df.empty:
            raise ValueError("output_df is empty or missing")

        for row_idx, row in tqdm(output_df.iterrows(), desc = "Loading ..."):
            print(f"🔄 Processing row {row_idx} (patient{row_idx+3})")
            
            # Step 1: Get the patient tab data
            sheet_name = f"patient{row_idx+3}"
            
            try:
                patient_df = self.google_sheets_api.get_df_from_tab(
                    spreadsheet_id=sheets_reporter_id,
                    spreadsheet_range_name=sheet_name,
                    spreadsheet_has_index=False,
                )
            except Exception as e:
                print(f"⚠️ Could not retrieve sheet {sheet_name}: {e}")
                continue
            
            if patient_df.empty:
                print(f"⚠️ Sheet {sheet_name} is empty, skipping")
                continue
            
            # Step 2: Get the last 12 columns with information
            patient_df, start_col_idx = self._get_last_populated_columns(patient_df, num_cols=12)
        
            # Step 3: Check processing conditions
            likert_cols = ["Coherence", "Emotional Resonance", "Perceived Helpfulness", "Motivational Impact", "Engagement"]
            
            # Convert w_new to numeric
            patient_df['w_new'] = pd.to_numeric(patient_df['w_new'], errors='coerce')
            patient_df[likert_cols] = patient_df[likert_cols].astype(float)
            
            # Check if w_new is all zeros and likert columns have scores
            w_new_all_zeros = (patient_df['w_new'] == 0.0).all()
            likert_has_scores = (patient_df[likert_cols] == 0.0).all().all()
            
            if not w_new_all_zeros or likert_has_scores:
                print(f"⚠️ Patient {sheet_name}: Conditions not met for processing")
                continue
            
            # Step 4: Calculate composite scores and update w_new
            patient_df = self._calculate_composite_and_update_weights(patient_df, likert_cols)
            
            # Update the patient sheet with new weights (only the 12 columns in their original position)
            self._update_patient_sheet_columns(
                df             = patient_df,
                spreadsheet_id = sheets_reporter_id,
                tab_name       = sheet_name,
                start_col_idx  = start_col_idx
            )

         ## _____________________________________________________________________________________________________________________ ##
        for row_idx, row in tqdm(output_df.iterrows(), desc = "Loading..."):
            print(f"🔄 Processing row {row_idx} (patient{row_idx+3})")
            
            # Step 1: Get the patient tab data
            sheet_name = f"patient{row_idx+3}"
            
            try:
                patient_df = self.google_sheets_api.get_df_from_tab(
                    spreadsheet_id         = sheets_reporter_id,
                    spreadsheet_range_name = sheet_name,
                    spreadsheet_has_index  = False,
                )


            except Exception as e:
                print(f"⚠️ Could not retrieve sheet {sheet_name}: {e}")
                continue
            
            if patient_df.empty:
                print(f"⚠️ Sheet {sheet_name} is empty, skipping")
                continue
            
            # Step 2: Get the last 12 columns with information
            patient_df, start_col_idx = self._get_last_populated_columns(patient_df, num_cols=12)


            # Check if w_new is all zeros and likert columns have scores
            patient_df['w_new'] = pd.to_numeric(patient_df['w_new'], errors='coerce')
            w_new_all_zeros = (patient_df['w_new'] == 0.0).all()

            if w_new_all_zeros : 
                print(f"⚠️ Patient {sheet_name}: Conditions not met for processing")
                continue
            
            # Step 5: Check meeting progression and notes availability
            current_meeting_idx = int(patient_df.loc[0,'meeting'])
            questionnaire, meeting_notes = self._check_meeting_progression(row, current_meeting_idx)

            if meeting_notes in self.__null_values :
                print(f"⚠️ Patient {sheet_name}: No next meeting notes available")
                continue

            print(f"✅ Processing meeting progression: Meeting{current_meeting_idx} → Meeting{current_meeting_idx + 1}")
            
            # Step 6: Replace questions using OpenAI
            patient_df = self._replace_lowest_scoring_questions(
                df            = patient_df, 
                meeting_notes = meeting_notes,
                prompt        = prompt,
                system_role   = system_role,
                user_role     = user_role, 
                requirements  = requirements,
                examples      = examples
            )
            
        
            # Step 7: Update patient dataframe
            patient_df = legacy.advance_meeting(patient_df, current_meeting_idx)

        
            # Step 8: Update patient sheet with new questions
            self._update_patient_sheet_columns(
                df             = patient_df,
                spreadsheet_id = sheets_reporter_id,
                tab_name       = sheet_name,
                start_col_idx  = start_col_idx + 12 # new questionnaire
            )

            # Apply formatting
            self.google_sheets_api.format_sheet_tab(
                df             = patient_df,
                spreadsheet_id = sheets_reporter_id, 
                tab_name       = sheet_name, 
                start_col_idx  = start_col_idx + 12 # new questionnaire
            )
            
            # Step 9: Merge questionnaire and update output tab
            merged_questionnaire = self._merge_categories(patient_df)
            
            # Update the next meeting's task column
            next_task_col = f"meeting{current_meeting_idx + 1}_task1"
            col_idx = self._find_column_index(output_df, next_task_col)
            
            if col_idx is not None:
                self.google_sheets_api.update_cell(
                    spreadsheet_id = sheets_reporter_id,
                    tab_name       = sheets_reporter_tab_output.split("!")[0], # output!A2:AH --> output,
                    row            = row_idx + 3,  # adjust for 0-index + header
                    col            = col_idx + 1,  # Google Sheets is 1-indexed
                    value          = merged_questionnaire
                )
                
            print(f"✅ Completed processing for {sheet_name}")
            

    def _get_last_populated_columns(self, df, num_cols=12):
        """Get the last 12 columns that contain data and return their starting position"""
        return legacy.get_last_populated_columns(df, num_cols=num_cols)

    def _update_patient_sheet_columns(self, df, spreadsheet_id, tab_name, start_col_idx):
        """Update only the specific columns in the patient sheet at their original position"""
        # Convert the DataFrame to a range that can be updated
        # Google Sheets uses 1-based indexing, so add 1 to start_col_idx
        start_col_letter = self._column_number_to_letter(start_col_idx + 1)
        end_col_letter = self._column_number_to_letter(start_col_idx + len(df.columns))
        
        # Create the range (e.g., "M1:X100" for columns M through X)
        range_name = f"{start_col_letter}1:{end_col_letter}{len(df) + 1}"  # +1 for header
        
        # Convert DataFrame to values for Google Sheets API
        values = [df.columns.tolist()] + df.values.tolist()
        
        # Update the specific range
        self.google_sheets_api.update_range(
            spreadsheet_id = spreadsheet_id,
            tab_name       = tab_name,
            range_name     = range_name,
            values         = values
        )

    def _column_number_to_letter(self, col_num):
        """Convert column number to letter (1=A, 2=B, ..., 27=AA, etc.)"""
        return legacy.column_number_to_letter(col_num)

    def _calculate_composite_and_update_weights(self, df, likert_cols):
        """Calculate composite scores and update w_new weights (legacy rule, see legacy.algorithm)."""
        return legacy.calculate_composite_and_update_weights(df, likert_cols)

    def _check_meeting_progression(self, row, current_meeting_idx):
        """Check current meeting number and if next meeting notes are available"""
        current_meeting_idx_str = f"meeting{current_meeting_idx}"
        next_meeting_idx_str    = f"meeting{current_meeting_idx+1}"

        if current_meeting_idx == 0 : 
            questionnaire = row["task0"]
        else : 
            questionnaire = row[f"{current_meeting_idx_str}_task1"]

        meeting_notes = row[ f"{next_meeting_idx_str}_notes"]

        return questionnaire, meeting_notes
        

    def _replace_lowest_scoring_questions(self, df, meeting_notes, prompt, system_role, user_role, requirements, examples):
        """Replace 2 lowest scoring questions per category using OpenAI (legacy rule)."""
        def generate(cat, existing_questions):
            variables = {
                "meeting_notes"      : meeting_notes,
                "existing_questions" : existing_questions,
                "category"           : cat
            }
            return self.openai_api.execute_custom_prompt(
                prompt       = prompt,
                variables    = variables,
                system_role  = system_role,
                user_role    = user_role,
                requirements = requirements,
                examples     = examples
            )

        def on_mismatch(cat, got, expected):
            print(f"⚠️ OpenAI returned {got} questions, expected {expected} for category {cat}")

        return legacy.replace_lowest_scoring_questions(df, generate, on_count_mismatch=on_mismatch)


    def _merge_categories(self, df):
        """Merge all categories and questions into Greek text format"""
        return legacy.merge_categories(df)


    def _find_column_index(self, df, column_name):
        """Find the index of a column by name"""
        try:
            return df.columns.get_loc(column_name)
        except KeyError:
            print(f"⚠️ Column '{column_name}' not found")
            return None
        


    def run_task1_analyze_results(self):
        tqdm.pandas()
        ## _______________ *** Configuration (attributes) *** _______________ #
        sheets_reporter_id          = self.mk1.config.get("google_sheets", "reporter_id")
        sheets_reporter_tab_output  = self.mk1.config.get("google_sheets", "reporter_tab_output")

        ## _____________________________________________________________________________________________________________________ ##
        # get the raw task0 content (assuming first col = metadata, second col = big text)
        output_df = self.google_sheets_api.get_df_from_tab(
            spreadsheet_id         = sheets_reporter_id,
            spreadsheet_range_name = sheets_reporter_tab_output,
            spreadsheet_has_index  = False,
        )

        if output_df.empty:
            raise ValueError("output_df is empty or missing")


        ## _____________________________________________________________________________________________________________________ ##
        for row_idx, row in tqdm(output_df.iterrows(), desc = "Loading..."):
            print(f"🔄 Processing row {row_idx} (patient{row_idx+3})")
            
            # Step 1: Get the patient tab data
            sheet_name = f"patient{row_idx+3}"
            
            try:
                patient_df = self.google_sheets_api.get_df_from_tab(
                    spreadsheet_id         = sheets_reporter_id,
                    spreadsheet_range_name = sheet_name,
                    spreadsheet_has_index  = False,
                )

            except Exception as e:
                print(f"⚠️ Could not retrieve sheet {sheet_name}: {e}")
                continue
            
            if patient_df.empty:
                print(f"⚠️ Sheet {sheet_name} is empty, skipping")
                continue
            
            # Step 2: Split all the dataframe in equal dataframes of 12 columns (20 rows each meeting)
            # Each meeting has 20 questions (4 questions per 5 categories)
            cols_per_meeting = 12
            total_cols      = patient_df.shape[1]
            num_meetings    = total_cols // cols_per_meeting

            meeting_dataframes = []

            for meeting_idx in range(num_meetings):
                start_idx             = meeting_idx * cols_per_meeting
                end_idx               = start_idx + cols_per_meeting
                meeting_df            = patient_df.iloc[:, start_idx:end_idx].copy()  # slice columns
                meeting_df['meeting'] = meeting_idx
                meeting_dataframes.append(meeting_df)
            
            print(f"   📊 Split into {len(meeting_dataframes)} meetings")
            
            # Step 3: Process weight evolution (w -> w_new chain)
            for i, df in enumerate(meeting_dataframes):
                if i == 0:
                    # First meeting: w stays as is, w_new is the updated weight
                    pass
                else:
                    # Subsequent meetings: w becomes the w_new from previous meeting
                    df['w'] = meeting_dataframes[i-1]['w_new'].values
            
            # Step 4: Create unique question registry and timeseries
            question_registry = {}
            question_id_counter = 1
            
            # Step 4.1: Identify all unique questions across all meetings
            for meeting_idx, df in enumerate(meeting_dataframes):
                for _, question_row in df.iterrows():
                    question_text  = question_row['question_text']
                    category       = question_row['category']
                    category_name  = question_row['category_name']
                    q_number       = question_row['q']
                    
                    # Create a unique identifier for this question
                    question_key = (category, q_number, question_text)
                    
                    if question_key not in question_registry:
                        question_registry[question_key] = {
                            'question_id'   : f"Q{question_id_counter:03d}",
                            'category'      : category,
                            'category_name' : category_name,
                            'q_number'      : q_number,
                            'question_text' : question_text,
                            'timeseries'    : {}
                        }
                        question_id_counter += 1
            
            # Step 4.2: Build timeseries for each question
            for meeting_idx, df in enumerate(meeting_dataframes):
                for _, question_row in df.iterrows():
                    question_text = question_row['question_text']
                    category = question_row['category']
                    q_number = question_row['q']
                    
                    question_key = (category, q_number, question_text)
                    
                    if question_key in question_registry:
                        question_registry[question_key]['timeseries'][meeting_idx] = {
                            'w': question_row['w'],
                            'w_new': question_row['w_new'],
                            'Coherence': question_row['Coherence'],
                            'Emotional_Resonance': question_row['Emotional Resonance'],
                            'Perceived_Helpfulness': question_row['Perceived Helpfulness'],
                            'Motivational_Impact': question_row['Motivational Impact'],
                            'Engagement': question_row['Engagement']
                        }
            
            # Step 5: Identify question changes between meetings
            question_changes = []
            
            for meeting_idx in range(1, len(meeting_dataframes)):
                current_meeting = meeting_dataframes[meeting_idx]
                previous_meeting = meeting_dataframes[meeting_idx - 1]
                
                # Group by category and q_number to compare
                for category in current_meeting['category'].unique():
                    for q_num in range(1, 5):  # Questions 1-4 for each category
                        
                        # Get questions from both meetings
                        curr_question = current_meeting[
                            (current_meeting['category'] == category) & 
                            (current_meeting['q'] == q_num)
                        ]['question_text'].iloc[0] if len(current_meeting[
                            (current_meeting['category'] == category) & 
                            (current_meeting['q'] == q_num)
                        ]) > 0 else None
                        
                        prev_question = previous_meeting[
                            (previous_meeting['category'] == category) & 
                            (previous_meeting['q'] == q_num)
                        ]['question_text'].iloc[0] if len(previous_meeting[
                            (previous_meeting['category'] == category) & 
                            (previous_meeting['q'] == q_num)
                        ]) > 0 else None
                        
                        # Check if questions are different
                        if curr_question != prev_question and curr_question is not None and prev_question is not None:
                            question_changes.append({
                                'meeting_transition': f"{meeting_idx-1} -> {meeting_idx}",
                                'category': category,
                                'q_number': q_num,
                                'old_question': prev_question,
                                'new_question': curr_question
                            })
            
            # Step 6: Create wide-format timeseries dataframe (one row per question)
            wide_timeseries_data = []

            for question_key, question_info in question_registry.items():
                row_data = {
                    'patient_id': f"patient{row_idx+3}",
                    'question_id': question_info['question_id'],
                    'category': question_info['category'],
                    'category_name': question_info['category_name'],
                    'q_number': question_info['q_number'],
                    'question_text': question_info['question_text']
                }
                
                # Add columns for each meeting
                for meeting_idx in range(len(meeting_dataframes)):
                    metrics = question_info['timeseries'].get(meeting_idx, None)
                    if metrics is not None:
                        row_data[f'w_{meeting_idx}'] = metrics['w']
                        row_data[f'Coherence_{meeting_idx}'] = metrics['Coherence']
                        row_data[f'Emotional_Resonance_{meeting_idx}'] = metrics['Emotional_Resonance']
                        row_data[f'Perceived_Helpfulness_{meeting_idx}'] = metrics['Perceived_Helpfulness']
                        row_data[f'Motivational_Impact_{meeting_idx}'] = metrics['Motivational_Impact']
                        row_data[f'Engagement_{meeting_idx}'] = metrics['Engagement']
                    else:
                        # Fill with NaN if the question didn't exist in this meeting
                        row_data[f'w_{meeting_idx}'] = None
                        row_data[f'Coherence_{meeting_idx}'] = None
                        row_data[f'Emotional_Resonance_{meeting_idx}'] = None
                        row_data[f'Perceived_Helpfulness_{meeting_idx}'] = None
                        row_data[f'Motivational_Impact_{meeting_idx}'] = None
                        row_data[f'Engagement_{meeting_idx}'] = None

                wide_timeseries_data.append(row_data)

            timeseries_df = pd.DataFrame(wide_timeseries_data)
            
            # Step 7: Print summary
            print(f"   📈 Question Registry Summary:")
            print(f"      - Total unique questions: {len(question_registry)}")
            print(f"      - Question changes detected: {len(question_changes)}")
            print(f"      - Timeseries data points: {len(timeseries_df)}")
            
            if question_changes:
                print(f"   🔄 Question Changes:")
                for change in question_changes:
                    print(f"      - Meeting {change['meeting_transition']}, Category {change['category']}, Q{change['q_number']}")
                    print(f"        Old: {change['old_question'][:60]}...")
                    print(f"        New: {change['new_question'][:60]}...")
            
            # Step 8: Save results
            os.makedirs("./data", exist_ok=True)
            output_file = f"./data/timeseries_{sheet_name}.csv"
            timeseries_df.to_csv(output_file, index=False)
            print(f"   💾 Saved timeseries data to {output_file}")
            
            # Save question registry
            registry_file = f"./data/question_registry_{sheet_name}.json"
            import json
            with open(registry_file, 'w', encoding='utf-8') as f:
                # Convert to JSON-serializable format
                registry_json = {}
                for key, value in question_registry.items():
                    registry_json[f"{key[0]}_{key[1]}_{hash(key[2]) % 10000}"] = value
                json.dump(registry_json, f, ensure_ascii=False, indent=2)
            print(f"   💾 Saved question registry to {registry_file}")
            
            print(f"✅ Completed processing {sheet_name}")
            print("-" * 80)

    def run_task1_visualize_results(self, save_dir="./outputs/figures"):
        """
        Visualize patient question responses and weights over meetings.
        Saves all plots automatically (no plt.show()).
        Designed for many meetings without huge legends.
        """
        os.makedirs(save_dir, exist_ok=True)

        data_files = [f for f in os.listdir("./data") if f.endswith(".csv")]

        for file in data_files:
            df = pd.read_csv(f"./data/{file}")
            weight_cols = [col for col in df.columns if col.startswith("w_")]

            for patient_id, patient_df in df.groupby("patient_id"):
                fig, axes = plt.subplots(2, 2, figsize=(16, 12))
                axes = axes.flatten()

                # 1️⃣ Heatmap of question weights over meetings
                heatmap_df = patient_df.set_index("question_id")[weight_cols].fillna(0)
                sns.heatmap(
                    heatmap_df,
                    cmap="viridis",
                    cbar_kws={"label": "Weight"},
                    ax=axes[0]
                )
                axes[0].set_title(f"Patient {patient_id} - Question Weights Over Meetings")
                axes[0].set_xlabel("Meeting")
                axes[0].set_ylabel("Question ID")

                # 2️⃣ Median + quantiles of weights per meeting (no individual legend)
                weights_only = patient_df[weight_cols].replace(0, pd.NA)
                median = weights_only.median()
                q25 = weights_only.quantile(0.25)
                q75 = weights_only.quantile(0.75)

                axes[1].plot(weight_cols, median, marker="o", label="Median")
                axes[1].fill_between(weight_cols, q25, q75, color="lightblue", alpha=0.3, label="25-75th percentile")
                axes[1].set_title("Weights Evolution per Meeting (Median & 25-75% Quantile)")
                axes[1].set_xlabel("Meeting")
                axes[1].set_ylabel("Weight")
                axes[1].legend()

                # 3️⃣ Question Stability / Volatility
                volatility = patient_df[weight_cols].std(axis=1)
                sns.heatmap(
                    volatility.to_frame(name="volatility"),
                    cmap="magma",
                    annot=True,
                    fmt=".2f",
                    cbar_kws={"label": "Std Dev of Weight"},
                    ax=axes[2]
                )
                axes[2].set_title("Question Volatility Across Meetings")
                axes[2].set_xlabel("Volatility")
                axes[2].set_ylabel("Question ID")


                # 4️⃣ Distribution of weights per meeting (violin plot)
                violin_df = patient_df.melt(id_vars=["question_id"], value_vars=weight_cols, var_name="meeting", value_name="weight")
                violin_df = violin_df[violin_df["weight"] > 0]  # ignore zeros
                sns.violinplot(x="meeting", y="weight", data=violin_df, ax=axes[3], inner="quartile", color="green")
                axes[3].set_title("Weight Distribution per Meeting")
                axes[3].set_xlabel("Meeting")
                axes[3].set_ylabel("Weight")
                axes[3].tick_params(axis="x", rotation=90)

                plt.tight_layout()

                # Save plot automatically
                plot_file = os.path.join(save_dir, f"{file.replace('.csv','')}_patient_{patient_id}.png")
                plt.savefig(plot_file)
                plt.close(fig)








    

    def run(self):
        operation = self.args.operation

        # Optional OAuth refresh via Dropbox (off by default):
        # self._refresh_tokens()

        runners = {
            "task0": self.run_task0,
            "task1_preparation": self.run_task1_preparation,
            "task1": self.run_task1,
            "task1_analyze_results": self.run_task1_analyze_results,
            "task1_visualize_results": self.run_task1_visualize_results,
        }
        if operation not in runners:
            raise ValueError(
                f"Unknown operation={operation!r}. "
                f"Choose one of: {', '.join(runners)}"
            )
        self.run_initialization()
        runners[operation]()


def main() -> None:
    """CLI entry used by ``main.py`` and ``python -m adaptive_questionnaires``."""
    Controller(MkI.get_instance(_logging=True)).run()


if __name__ == "__main__":
    main()

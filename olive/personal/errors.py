"""Safe native validation guidance; arbitrary parser/provider text is not public."""
class PersonalOperationError(ValueError):
    pass

MESSAGES={
 'Choose a valid IANA timezone','This local time does not exist during the timezone transition',
 'This local time occurs twice; choose the first or second occurrence','Time offset does not match the selected timezone',
 'End must be after start (all-day end is exclusive)','A name or title is required','Invalid email address',
 'This record changed. Reload or compare before saving.','This record changed. Review deletion again.',
 'Move linked events and change the default calendar before deleting this calendar',
 'Use the reviewed occurrence deletion action','Use the reviewed event deletion action to cancel a series',
 'Exception does not identify an original occurrence in this series','Contacts changed; review a new merge',
 'Review conflicting fields before merging','Import preview expired or was already committed',
 'Import has errors; explicitly select valid rows or cancel','Preview exceeds 500 KB; split the source into smaller reviewed batches',
 'Linked project no longer exists','Task changed; review scheduling again',
 'Unlink the existing calendar block before scheduling another','Unsupported recurrence field',
 'Action was not approved','Task cancelled by user','Personal record not found',
 'Number is outside its supported range','Use a date in YYYY-MM-DD format',
 'This reminder is no longer active','Working hours must end after they start',
 'Reopen the task before scheduling a new work block',
}

def guidance(result,permissions):
    if result.summary in MESSAGES:return result.summary
    if result.summary.startswith('Permission denied: ') and result.summary.removeprefix('Permission denied: ') in permissions:return result.summary
    if result.error_type=='RevisionConflict':return 'This record changed. Reload or compare before saving.'
    if result.error_type=='StaleApproval':return 'The action changed. Review the current proposal again.'
    return 'The native operation could not complete. Check the fields, linked records and current revision; no successful change was confirmed.'

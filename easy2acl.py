#!/usr/bin/env python3

#
# easy2acl.py - Convert data from EasyChair for use with ACLPUB
#
# Original Author: Nils Blomqvist
# Forked/modified by: Asad Sayeed
# Further modifications and docs (for 2019 Anthology): Matt Post
#
# Please see the documentation in the README file at http://github.com/acl-org/easy2acl.

import os
import re
import sys

from csv import DictReader
from glob import glob
from shutil import copy, rmtree
from unicode_tex import unicode_to_tex
from pybtex.database import BibliographyData, Entry


def texify(string):
    """Return a modified version of the argument string where non-ASCII symbols have
    been converted into LaTeX escape codes.

    """
    return ' '.join(map(unicode_to_tex, string.split()))


#,----
#| Metadata
#`----
metadata = { 'chairs': [] }
with open('meta') as metadata_file:
    for line in metadata_file:
        key, value = line.rstrip().split(maxsplit=1)
        if key == 'chairs':
            metadata[key].append(value)
        else:
            metadata[key] = value

for key in 'abbrev title booktitle month year location publisher chairs bib_url'.split():
    if key not in metadata:
        print('Fatal: missing key "{}" from "meta" file'.format(key))
        sys.exit(1)

match = re.match(r'https://www.aclweb.org/anthology/([A-Z])(\d\d)-(\d+)%0(\d+)d', metadata['bib_url'])
if match is None:
    print("Fatal: bib_url field ({}) in 'meta' file has wrong pattern".format(metadata['bib_url']), file=sys.stderr)
    sys.exit(1)
anthology_collection, anthology_year, anthology_volume, anthology_paper_width = match.groups()

#,----
#| Append each accepted submission, as a tuple, to the 'accepted' list.
#`----
accepted = []

with open('accepted') as accepted_file:
    for line in accepted_file:
        entry = line.rstrip().split("\t")
        # modified here to filter out the rejected files rather than doing
        # that by hand
        if entry[-1] == 'ACCEPT':
            submission_id = entry[0]
            title = entry[1]

            accepted.append((submission_id, title))
    print("Found ", len(accepted), " accepted files")

#,----
#| Append each submission, as a tuple, to the 'submissions' list.
#`----
submissions = []

with open('submissions') as submissions_file:
    for line in submissions_file:
        entry = line.rstrip().split("\t")
        submission_id = entry[0]
        authors = entry[1].replace(' and', ',').split(', ')
        title = entry[2]

        submissions.append((submission_id, title, authors))
    print("Found ", len(submissions), " submitted files")

# Read abstracts
abstracts = {}
if os.path.exists('submission.csv'):
    with open('submission.csv') as csv_file:
        d = DictReader(csv_file)
        for row in d:
            abstracts[row['#']] = row['abstract']
    print('Found ', len(abstracts), 'abstracts')

#
# Find all relevant PDFs
#

# The PDF of the full proceedings
full_pdf_file = 'pdf/{abbrev}_{year}.pdf'.format(abbrev=metadata['abbrev'],
                                                 year=metadata['year'])
if not os.path.exists(full_pdf_file):
    print("Fatal: could not find full volume PDF '{}'".format(full_pdf_file))
    sys.exit(1)

# The PDF of the frontmatter
frontmatter_pdf_file = 'pdf/{abbrev}_{year}_frontmatter.pdf'.format(abbrev=metadata['abbrev'],
                                                                    year=metadata['year'])
if not os.path.exists(frontmatter_pdf_file):
    print("Fatal: could not find frontmatter PDF file '{}'".format(frontmatter_pdf_file))
    sys.exit(1)

# File locations of all PDFs (seeded with PDF for frontmatter)
pdfs = { '0': frontmatter_pdf_file }
for pdf_file in glob('pdf/{abbrev}_{year}_paper_*.pdf'.format(abbrev=metadata['abbrev'], year=metadata['year'])):
    submission_id = pdf_file.split('_')[-1].replace('.pdf', '')
    pdfs[submission_id] = pdf_file

# List of accepted papers (seeded with frontmatter)
final_papers = [ ('0', metadata['booktitle'], metadata['chairs']) ]

for a in accepted:
    for s in submissions:
        if s[0] == a[0] and s[1] == a[1]:
            final_papers.append(s)
            break

#
# Create Anthology tarball
#

# Create destination directories
for dir in ['bib', 'pdf']:
    dest_dir = os.path.join('proceedings/cdrom', dir)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

# Copy over "meta" file
print('COPYING meta -> proceedings/meta', file=sys.stderr)
copy('meta', 'proceedings/meta')

paper_id = 0  # maps system paper IDs (random) to Anthology IDs (starting at 1)
final_bibs = []
for entry in final_papers:
    submission_id, paper_title, authors = entry
    authors = ' and '.join(authors)
    if not submission_id in pdfs:
        print('Fatal: no PDF found for paper', paper_id, file=sys.stderr)
        sys.exit(1)

    pdf_path = pdfs[submission_id]
    formatted_id = '{paper_id:0{width}d}'.format(paper_id=paper_id, width=anthology_paper_width)
    dest_path = 'proceedings/cdrom/pdf/{letter}{year}-{workshop_id}{paper_id}.pdf'.format(letter=anthology_collection, year=anthology_year, workshop_id=anthology_volume, paper_id=formatted_id)
    paper_id += 1

    copy(pdf_path, dest_path)
    print('COPYING', pdf_path, '->', dest_path, file=sys.stderr)

    bib_path = dest_path.replace('pdf', 'bib')
    if not os.path.exists(os.path.dirname(bib_path)):
        os.makedirs(os.path.dirname(bib_path))

    anthology_id = os.path.basename(dest_path).replace('.pdf', '')

    bib_type = 'inproceedings' if submission_id != '0' else 'proceedings'
    bib_entry = Entry(bib_type, [
        ('author', texify(authors)),
        ('title', paper_title),
        ('year', metadata['year']),
        ('month', metadata['month']),
        ('address', metadata['location']),
        ('publisher', metadata['publisher']),
    ])

    # Add the abstract if present
    if submission_id in abstracts:
        bib_entry.fields['abstract'] = abstracts.get(submission_id)

    # Add booktitle for non-proceedings entries
    if bib_type == 'inproceedings':
        bib_entry.fields['booktitle'] = metadata['booktitle']

    try:
        bib_string = BibliographyData({ anthology_id: bib_entry }).to_string('bibtex')
    except TypeError as e:
        print('Fatal: Error in BibTeX-encoding paper', submission_id, file=sys.stderr)
        sys.exit(1)
    final_bibs.append(bib_string)
    with open(bib_path, 'w') as out_bib:
        print(bib_string, file=out_bib)
        print('CREATED', bib_path)

# Write the volume-level bib with all the entries
dest_bib = 'proceedings/cdrom/{abbrev}-{year}.bib'.format(abbrev=metadata['abbrev'],
                                                          year=metadata['year'])
with open(dest_bib, 'w') as whole_bib:
    print('\n'.join(final_bibs), file=whole_bib)
    print('CREATED', dest_bib)

# Copy over the volume-level PDF
dest_pdf = dest_bib.replace('bib', 'pdf')
print('COPYING', full_pdf_file, '->', dest_pdf, file=sys.stderr)
copy(full_pdf_file, dest_pdf)

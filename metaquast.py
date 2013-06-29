#!/usr/bin/env python

############################################################################
# Copyright (c) 2011-2013 Saint-Petersburg Academic University
# All Rights Reserved
# See file LICENSE for details.
############################################################################

from __future__ import with_statement

RELEASE_MODE = False

import getopt
import os
import shutil
import sys
from libs import qconfig, qutils, fastaparser
from libs.qutils import assert_file_exists

from libs.log import get_logger
logger = get_logger('metaquast')
logger.set_up_console_handler(debug=not RELEASE_MODE)

import quast

from site import addsitedir
addsitedir(os.path.join(qconfig.LIBS_LOCATION, 'site_packages'))

COMBINED_REF_FNAME = 'combined_reference.fasta'


def usage():
    print >> sys.stderr, "Options:"
    print >> sys.stderr, "-o            <dirname>      Directory to store all result file. Default: quast_results/results_<datetime>"
    print >> sys.stderr, "-R            <filename>     Reference genomes (accepts multiple fasta files with multiple sequences each)"
    print >> sys.stderr, "-G  --genes   <filename>     Annotated genes file"
    print >> sys.stderr, "-O  --operons <filename>     Annotated operons file"
    print >> sys.stderr, "--min-contig  <int>          Lower threshold for contig length [default: %s]" % qconfig.min_contig
    print >> sys.stderr, ""
    print >> sys.stderr, "Advanced options:"
    print >> sys.stderr, "--threads <int>                   Maximum number of threads [default: number of CPUs]"
    print >> sys.stderr, "--gage                            Starts GAGE inside QUAST (\"GAGE mode\")"
    print >> sys.stderr, "--contig-thresholds <int,int,..>  Comma-separated list of contig length thresholds [default: %s]" % qconfig.contig_thresholds
    print >> sys.stderr, "--gene-finding                    Uses MetaGeneMark for gene finding"
    print >> sys.stderr, "--gene-thresholds <int,int,..>    Comma-separated list of threshold lengths of genes to search with Gene Finding module"
    print >> sys.stderr, "                                  [default is %s]" % qconfig.genes_lengths
    print >> sys.stderr, "--eukaryote                       Genome is an eukaryote"
    print >> sys.stderr, "--est-ref-size <int>              Estimated reference size (for computing NGx metrics without a reference)"
    print >> sys.stderr, "--scaffolds                       Provided assemblies are scaffolds"
    print >> sys.stderr, "--use-all-alignments              Computes Genome fraction, # genes, # operons metrics in compatible with QUAST v.1.* mode."
    print >> sys.stderr, "                                  By default, QUAST filters Nucmer\'s alignments to keep only best ones"
    print >> sys.stderr, "--ambiguity-usage <none|one|all>  Uses none, one, or all alignments of a contig with multiple equally good alignments."
    print >> sys.stderr, "                                  [default is %s]" % qconfig.ambiguity_usage
    print >> sys.stderr, "--strict-NA                       Breaks contigs by any misassembly event to compute NAx and NGAx."
    print >> sys.stderr, "                                  By default, QUAST breaks contigs only by extensive misassemblies (not local ones)"
    print >> sys.stderr, "-h  --help                        Prints this message"


def _partition_contigs(contigs_fpaths, ref_fpaths, corrected_dirpath, alignments_fpath):
    # not_aligned_anywhere_dirpath = os.path.join(output_dirpath, 'contigs_not_aligned_anywhere')
    # if os.path.isdir(not_aligned_anywhere_dirpath):
    #     os.rmdir(not_aligned_anywhere_dirpath)
    # os.mkdir(not_aligned_anywhere_dirpath)

    not_aligned_fpaths = []
    # array of fpaths for each reference
    partitions = dict([(os.path.basename(ref_fpath), []) for ref_fpath in ref_fpaths])

    for contigs_fpath in contigs_fpaths:
        contigs_path, ext = os.path.splitext(contigs_fpath)
        contigs_name = os.path.basename(contigs_path)
        not_aligned_fpath = contigs_path + '_not_aligned_anywhere' + ext
        contigs = {}
        aligned_contig_names = set()

        alignments_tsv_fpath = alignments_fpath % os.path.splitext(os.path.basename(contigs_fpath))[0]
        with open(alignments_tsv_fpath) as f:
            for line in f.readlines():
                values = line.split()
                ref_fname = values[0]
                ref_contigs_names = values[1:]
                ref_contigs_fpath = os.path.join(corrected_dirpath, contigs_name + '_to_' + ref_fname)

                for (cont_name, seq) in fastaparser.read_fasta(contigs_fpath):
                    if not cont_name in contigs.keys():
                        contigs[cont_name] = seq

                    if cont_name in ref_contigs_names:
                        # Collecting all aligned contigs names in order to futher extract not-aligned
                        aligned_contig_names.add(cont_name)
                        fastaparser.write_fasta(ref_contigs_fpath, [(cont_name, seq)], 'a')

                partitions[ref_fname].append(ref_contigs_fpath)

        # Exctraction not aligned contigs
        all_contigs_names = set(contigs.keys())
        not_aligned_contigs_names = all_contigs_names - aligned_contig_names
        fastaparser.write_fasta(not_aligned_fpath, [(name, contigs[name]) for name in not_aligned_contigs_names])

        not_aligned_fpaths.append(not_aligned_fpath)

    return partitions, not_aligned_fpaths


# class LoggingIndentFormatter(logging.Formatter):
#     def __init__(self, fmt):
#         logging.Formatter.__init__(self, fmt)
#
#     def format(self, record):
#         indent = '\t'
#         msg = logging.Formatter.format(self, record)
#         return '\n'.join([indent + x for x in msg.split('\n')])


def _start_quast_main(
        name, args, contigs_fpaths, reference_fpath=None,
        output_dirpath=None, exit_on_exception=True):
    args = args[:]

    args.extend(contigs_fpaths)

    if reference_fpath:
        args.append('-R')
        args.append(reference_fpath)

    if output_dirpath:
        args.append('-o')
        args.append(output_dirpath)

    import quast
    reload(quast)
    quast.logger.set_up_console_handler(debug=not RELEASE_MODE, indent_val=1)

    # nested_quast_console_handler = logging.StreamHandler(sys.stdout)
    # nested_quast_console_handler.setFormatter(
    #     LoggingIndentFormatter('%(message)s'))
    # nested_quast_console_handler.setLevel(logging.DEBUG)
    # log.addHandler(nested_quast_console_handler)

    # print 'quast.py ' + ' '.join(args)

    logger.info_to_file('(logging to ' +
                        os.path.join(output_dirpath,
                                     qconfig.LOGGER_DEFAULT_NAME + '.log)'))
    try:
        quast.main(args)

    except Exception, e:
        if exit_on_exception:
            logger.exception(e)
        else:
            msg = 'Error running quast.py' + (' ' + name if name else '')
            msg += ': ' + e.strerror
            if e.message:
                msg += ', ' + e.message
            logger.error(msg)


def main(args):
    libs_dir = os.path.dirname(qconfig.LIBS_LOCATION)
    if ' ' in libs_dir:
        logger.error(
            'QUAST does not support spaces in paths. \n' + \
            'You are trying to run it from ' + str(libs_dir) + '\n' + \
            'Please, put QUAST in a different directory, then try again.\n',
            to_stderr=True,
            exit_with_code=3)

    min_contig = qconfig.min_contig
    genes = ''
    operons = ''
    draw_plots = qconfig.draw_plots
    html_report = qconfig.html_report
    save_json = qconfig.save_json
    make_latest_symlink = True

    try:
        options, contigs_fpaths = getopt.gnu_getopt(args, qconfig.short_options, qconfig.long_options)
    except getopt.GetoptError, err:
        print >> sys.stderr, err
        print >> sys.stderr
        usage()
        sys.exit(2)

    if not contigs_fpaths:
        usage()
        sys.exit(2)

    ref_fpaths = []
    combined_ref_fpath = ''

    json_outputpath = None
    output_dirpath = None

    for opt, arg in options:
        # Yes, this is a code duplicating. Python's getopt is non well-thought!!
        if opt in ('-o', "--output-dir"):
            # Removing output dir arg in order to further
            # construct other quast calls from this options
            args.remove('-o')
            args.remove(arg)

            output_dirpath = os.path.abspath(arg)
            make_latest_symlink = False

        elif opt in ('-G', "--genes"):
            assert_file_exists(arg, 'genes')
            genes = arg

        elif opt in ('-O', "--operons"):
            assert_file_exists(arg, 'operons')
            operons = arg

        elif opt in ('-R', "--reference"):
            # Removing reference args in order to further
            # construct quast calls from this args with other reference options
            args.remove('-R')
            args.remove(arg)

            ref_fpaths = arg.split(',')
            for i, ref_fpath in enumerate(ref_fpaths):
                assert_file_exists(ref_fpath, 'reference')
                ref_fpaths[i] = ref_fpath

        elif opt in ('-M', "--min-contig"):
            min_contig = int(arg)

        elif opt in ('-j', '--save-json'):
            save_json = True

        elif opt in ('-J', '--save-json-to'):
            save_json = True
            make_latest_symlink = False
            json_outputpath = arg

        elif opt == '--no-plots':
            draw_plots = False

        elif opt == '--no-html':
            html_report = False

        elif opt in ('-h', "--help"):
            usage()
            sys.exit(0)

        elif opt in ('-T', "--threads"):
            pass

        elif opt in ('-t', "--contig-thresholds"):
            pass

        elif opt in ('-c', "--mincluster"):
            pass

        elif opt == "--est-ref-size":
            pass

        elif opt in ('-S', "--gene-thresholds"):
            pass

        elif opt in ('-s', "--scaffolds"):
            pass

        elif opt == "--gage":
            pass

        elif opt in ('-e', "--eukaryote"):
            pass

        elif opt in ('-f', "--gene-finding"):
            pass

        elif opt in ('-a', "--ambiguity-usage"):
            pass

        elif opt in ('-u', "--use-all-alignments"):
            pass

        elif opt in ('-n', "--strict-NA"):
            pass

        elif opt in ("-m", "--meta"):
            pass

        elif opt in ('-d', "--debug"):
            pass

        else:
            raise ValueError

    for c_fpath in contigs_fpaths:
        assert_file_exists(c_fpath, 'contigs')

    for contigs_fpath in contigs_fpaths:
        args.remove(contigs_fpath)

    # # Removing outout dir if exists
    # if output_dirpath:  # 'output dir was specified with -o option'
    #     if os.path.isdir(output_dirpath):
    #         shutil.rmtree(output_dirpath)

    # Directories
    output_dirpath, json_outputpath, existing_alignments = \
        quast._set_up_output_dir(output_dirpath, json_outputpath,
                                 make_latest_symlink, save_json)

    corrected_dirpath = os.path.join(output_dirpath, qconfig.corrected_dirname)

    logger.set_up_file_handler(output_dirpath)
    logger.info(' '.join(sys.argv))
    logger.start()

    # Where all pdfs will be saved
    all_pdf_filename = os.path.join(output_dirpath, qconfig.plots_filename)
    all_pdf = None

    ########################################################################

    from libs import reporting
    reload(reporting)

    if os.path.isdir(corrected_dirpath):
        shutil.rmtree(corrected_dirpath)
    os.mkdir(corrected_dirpath)

    # PROCESSING REFERENCES
    if ref_fpaths:
        logger.info('Processing references...')

        corrected_ref_fpaths = []

        combined_ref_fpath = os.path.join(corrected_dirpath, COMBINED_REF_FNAME)

        for ref_fpath in ref_fpaths:
            ref_fname = os.path.basename(ref_fpath)
            ref_name, ext = os.path.splitext(ref_fname)
            corr_name = qutils.correct_name(ref_name)

            for i, (name, seq) in enumerate(fastaparser.read_fasta(ref_fpath)):
                corr_fname = corr_name + '_' + qutils.correct_name(name) + ext
                corr_fpath = os.path.join(corrected_dirpath, corr_fname)
                corrected_ref_fpaths.append(corr_fpath)

                fastaparser.write_fasta(corr_fpath, [(corr_fname, seq)], 'a')
                fastaparser.write_fasta(combined_ref_fpath, [(corr_fname, seq)], 'a')
                logger.info('\t' + corr_fname + '\n')

        logger.info('\tAll references combined in ' + COMBINED_REF_FNAME)
        ref_fpaths = corrected_ref_fpaths

        logger.info('')

    ## removing from contigs' names special characters because:
    ## 1) Some embedded tools can fail on some strings with "...", "+", "-", etc
    ## 2) Nucmer fails on names like "contig 1_bla_bla", "contig 2_bla_bla" (it interprets as a contig's name only the first word of caption and gets ambiguous contigs names)
    logger.info('Processing contigs...')
    new_contigs_fpaths = []

    for i, contigs_fpath in enumerate(contigs_fpaths):
        contigs_fname = os.path.basename(contigs_fpath)
        corr_fname = quast.corrected_fname_for_nucmer(contigs_fname)
        corr_fpath = os.path.join(corrected_dirpath, corr_fname)
        if os.path.isfile(corr_fpath):  # in case of files with equal names
            i = 1
            basename, ext = os.path.splitext(corr_fname)
            while os.path.isfile(corr_fpath):
                i += 1
                corr_fpath = os.path.join(corrected_dirpath, os.path.basename(basename + '__' + str(i)) + ext)

        logger.info('\t%s ==> %s' % (contigs_fpath, os.path.basename(corr_fpath)))

        # Handle fasta
        lengths = fastaparser.get_lengths_from_fastafile(contigs_fpath)
        if not sum(l for l in lengths if l >= min_contig):
            logger.warning("Skipping %s because it doesn't contain contigs >= %d bp."
                           % (os.path.basename(contigs_fpath), min_contig))
            continue

        # correcting
        if not quast.correct_fasta(contigs_fpath, corr_fpath, min_contig):
            continue

        new_contigs_fpaths.append(corr_fpath)

        logger.info('')

    contigs_fpaths = new_contigs_fpaths

    if not contigs_fpaths:
        logger.error("None of assembly file contain correct contigs. "
                     "Please, provide different files or decrease --min-contig threshold.",
                     exit_with_code=4)

    # End of processing
    logger.info('Done preprocessing input.')

    # Running QUAST(s)
    args += ['--meta']

    if not ref_fpaths:
        # No references, running regular quast with MetaGenemark gene finder
        logger.info('')
        logger.info('No references provided, starting quast.py with MetaGeneMark gene finder')
        _start_quast_main(
            None,
            args,
            contigs_fpaths=contigs_fpaths,
            output_dirpath=os.path.join(output_dirpath, 'quast_output'),
            exit_on_exception=True)
        exit(0)

    # Running combined reference
    run_name = 'for the combined reference'
    logger.info('')
    logger.info('Starting quast.py ' + run_name + '...')

    _start_quast_main(run_name, args,
        contigs_fpaths=contigs_fpaths,
        reference_fpath=combined_ref_fpath,
        output_dirpath=os.path.join(output_dirpath, 'combined_quast_output'))

    # Partitioning contigs into bins aligned to each reference
    partitions, not_aligned_fpaths = _partition_contigs(
        contigs_fpaths, ref_fpaths, corrected_dirpath,
        os.path.join(output_dirpath, 'combined_quast_output', 'contigs_reports', 'alignments_%s.tsv'))

    for ref_fname, contigs_fpaths in partitions.iteritems():
        ref_name = os.path.splitext(os.path.basename(ref_fname))[0]

        logger.info('')
        if not contigs_fpaths:
            logger.info('No contigs are aligned to the reference ' + ref_name)
        else:
            run_name = 'for the contigs aligned to ' + ref_name
            logger.info('Starting quast.py ' + run_name)

            _start_quast_main(run_name, args,
                contigs_fpaths=contigs_fpaths,
                reference_fpath=os.path.join(corrected_dirpath, ref_fname),
                output_dirpath=os.path.join(output_dirpath, ref_name + '_quast_output'),
                exit_on_exception=False)

    # Finally running for the contigs that has not been aligned to any reference
    run_name = 'for the contigs not alined anywhere'
    logger.info('')
    logger.info('Starting quast.py ' + run_name + '...')

    _start_quast_main(run_name, args,
        contigs_fpaths=not_aligned_fpaths,
        output_dirpath=os.path.join(output_dirpath, 'not_aligned_quast_output'),
        exit_on_exception=False)

    quast._cleanup(corrected_dirpath)

    logger.info('')
    logger.info('MetaQUAST finished.')
    logger.finish_up()


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Exception, e:
        logger.exception(e)

















